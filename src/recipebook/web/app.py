"""The local web app: library, recipe form, intake (add, queue, review), settings, PDFs."""

from __future__ import annotations

import mimetypes
from dataclasses import asdict
from datetime import datetime
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import jinja2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ..config import Home, default_home
from ..intake.inbox import InboxWatcher
from ..intake.jobs import Job, JobStore
from ..intake.ocr import default_ocr
from ..intake.pipeline import Pipeline, Worker, finish_draft
from ..intake.structure import DEFAULT_LOCAL_MODEL, ClaudeStructurer, LocalStructurer
from ..library import Library
from ..model import Recipe
from ..render.book import BookOptions, build_book
from ..render.pdf import BINDINGS, render_recipe_pdf
from ..secrets import KeychainStore
from ..shopping import EntryError, merge, parse_numbers, recipes_on_pages
from ..style.glossary import GlossaryEntry
from ..style.housestyle import apply_house_style
from .forms import form_from_recipe, recipe_from_form

HERE = Path(__file__).parent
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
ACTIVE_STATES = ("queued", "reading", "structuring")

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(HERE / "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "recipe"


def pdf_filename(recipe: Recipe) -> str:
    number = f"no-{recipe.id}-" if recipe.id else ""
    return f"{number}{_slug(recipe.title)}.pdf"


def glossary_to_text(entries) -> str:
    return "\n".join(f"{e.preferred}: {', '.join(e.variants)}" for e in entries)


def glossary_from_text(text: str) -> list[GlossaryEntry]:
    """One entry per line: 'preferred name: variant, variant'."""
    entries = []
    for line in (text or "").splitlines():
        preferred, _, variants = line.partition(":")
        preferred = preferred.strip()
        if preferred:
            entries.append(GlossaryEntry(preferred, tuple(v.strip() for v in variants.split(",") if v.strip())))
    return entries


def create_app(
    home: Home | None = None,
    extra_hosts: frozenset[str] = frozenset(),
    *,
    ocr=None,
    key_store=None,
    structurer_for=None,
    url_client=None,
    start_worker: bool = True,
) -> FastAPI:
    home = (home or default_home()).ensure()
    library = Library(home.database)
    jobs = JobStore(home.database)
    keys = key_store or KeychainStore()
    allowed_hosts = LOCAL_HOSTS | set(extra_hosts)

    def default_structurer_for(name: str):
        if name == "claude":
            return ClaudeStructurer(api_key=keys.get())
        return LocalStructurer(model=library.get_setting("local_model", DEFAULT_LOCAL_MODEL))

    pipeline = Pipeline(jobs, library, home.originals, ocr or default_ocr(),
                        structurer_for or default_structurer_for, url_client=url_client)
    inbox = InboxWatcher(home.inbox, home.originals, jobs,
                         lambda: library.get_setting("default_structurer", "local"))
    worker = Worker(pipeline, before_each=[inbox.scan])

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()

    app = FastAPI(title="Recipe Book", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.pipeline = pipeline
    app.state.inbox = inbox
    app.state.jobs = jobs
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def local_requests_only(request: Request, call_next):
        """Refuse requests that a web page elsewhere could aim at this local server.

        The Host must be this machine (blocks DNS rebinding), and a form post must come
        from one of this app's own pages (blocks cross-site form posts).
        """
        host = request.headers.get("host", "")
        if urlsplit(f"//{host}").hostname not in allowed_hosts:
            return PlainTextResponse("This app only answers on this computer.", status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin is not None and urlsplit(origin).netloc != host:
                return PlainTextResponse("Form posts must come from this app.", status_code=403)
        return await call_next(request)

    def page(name: str, status: int = 200, **context) -> HTMLResponse:
        context.setdefault("review_count", jobs.needing_review())
        return HTMLResponse(_env.get_template(name).render(**context), status_code=status)

    @app.exception_handler(HTTPException)
    async def friendly_error(request: Request, error: HTTPException):
        heading = "Not found" if error.status_code == 404 else "Something went wrong"
        return page("error.html", error.status_code, heading=heading, message=error.detail)

    def styled(form, existing: Recipe | None = None) -> Recipe:
        return apply_house_style(recipe_from_form(form, existing), library.glossary())

    def form_page(recipe: Recipe | None, form: dict, status: int = 200, **context) -> HTMLResponse:
        return page(
            "recipe_form.html", status, recipe=recipe, form=form, categories=library.categories(), **context)

    def require(recipe_id: int) -> Recipe:
        recipe = library.get(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail=f"There is no recipe No. {recipe_id}.")
        return recipe

    def require_job(job_id: int) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="That item is no longer in the queue.")
        return job

    def require_draft(draft_id: int):
        draft = jobs.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="That draft no longer exists.")
        return draft

    # ---- library ----

    def library_context(q: str) -> dict:
        q = q.strip()
        total = len(library.list())
        if q:
            return dict(q=q, results=library.search(q), total=total, sections=[])
        summaries = library.list()
        categories = library.categories()
        sections = [(name, [s for s in summaries if s.category == name]) for name in categories]
        other = [s for s in summaries if s.category not in categories]
        if other:
            sections.append(("Other", other))
        return dict(q="", results=None, total=total, sections=sections)

    @app.get("/", response_class=HTMLResponse)
    def library_page(deleted: str = "", q: str = ""):
        return page("library.html", deleted=deleted, **library_context(q))

    @app.get("/search", response_class=HTMLResponse)
    def search_fragment(q: str = ""):
        """The library list alone, for filtering as you type."""
        return HTMLResponse(_env.get_template("_library_list.html").render(**library_context(q)))

    # ---- ingredient list ----

    @app.get("/ingredients", response_class=HTMLResponse)
    def ingredient_list(entry: str = "", mode: str = "pages", edition: int = 0):
        editions = library.editions()
        mode = "numbers" if mode == "numbers" or not editions else "pages"
        context = dict(entry=entry, mode=mode, editions=editions, edition_id=edition or (editions[0]["id"] if editions else 0))
        if not entry.strip():
            return page("ingredients.html", **context)
        try:
            numbers = parse_numbers(entry)
        except EntryError as error:
            return page("ingredients.html", 422, problem=str(error), **context)
        skipped: list[int] = []
        if mode == "pages":
            chosen = library.get_edition(context["edition_id"])
            if chosen is None:
                return page("ingredients.html", 422, problem="Export the book first; page numbers belong to an edition.", **context)
            numbers, skipped = recipes_on_pages(chosen["page_map"], numbers)
        recipes = [r for r in (library.get(n) for n in numbers) if r is not None]
        missing = [n for n in numbers if all(r.id != n for r in recipes)]
        if not recipes:
            what = "pages hold" if mode == "pages" else "numbers match"
            return page("ingredients.html", 422, problem=f"None of those {what} a recipe.", skipped=skipped, missing=missing, **context)
        merged = merge(recipes)
        return page("ingredients.html", recipes=recipes, merged=merged, text=merged.text(recipes),
                    skipped=skipped, missing=missing, **context)

    # ---- recipe form ----

    @app.get("/recipes/new", response_class=HTMLResponse)
    def new_recipe():
        blank = form_from_recipe(Recipe(title="", category=library.categories()[2]))
        return form_page(None, blank)

    @app.post("/recipes")
    async def create_recipe(request: Request):
        form = dict(await request.form())
        recipe = styled(form)
        missing = recipe.missing_for_save()
        if missing:
            return form_page(None, form, status=422, missing=missing)
        saved = library.save(recipe)
        return RedirectResponse(f"/recipes/{saved.id}?saved=1", status_code=303)

    @app.post("/recipes/preview")
    async def preview_recipe(request: Request):
        """Render the form as it stands, without saving."""
        form = dict(await request.form())
        existing = None
        if str(form.get("recipe_id", "")).isdigit():
            existing = library.get(int(form["recipe_id"]))
        recipe = styled(form, existing)
        if not recipe.title:
            recipe = recipe.model_copy(update={"title": "Untitled recipe"})
        data, _ = await run_in_threadpool(render_recipe_pdf, recipe)
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": 'inline; filename="preview.pdf"'})

    @app.get("/recipes/{recipe_id}", response_class=HTMLResponse)
    def edit_recipe(recipe_id: int, saved: str = ""):
        recipe = require(recipe_id)
        return form_page(recipe, form_from_recipe(recipe), saved=bool(saved))

    @app.post("/recipes/{recipe_id}")
    async def update_recipe(recipe_id: int, request: Request):
        existing = require(recipe_id)
        form = dict(await request.form())
        recipe = styled(form, existing)
        missing = recipe.missing_for_save()
        if missing:
            return form_page(existing, form, status=422, missing=missing)
        library.save(recipe)
        return RedirectResponse(f"/recipes/{recipe_id}?saved=1", status_code=303)

    @app.post("/recipes/{recipe_id}/delete")
    def delete_recipe(recipe_id: int):
        recipe = require(recipe_id)
        library.delete(recipe_id)
        return RedirectResponse(f"/?deleted={recipe.id}", status_code=303)

    # ---- PDF ----

    @app.get("/recipes/{recipe_id}/pdf")
    async def recipe_pdf(recipe_id: int, download: int = 0):
        """Show the recipe's PDF. With download=1, also keep a copy in the exports folder."""
        recipe = require(recipe_id)
        data, _ = await run_in_threadpool(render_recipe_pdf, recipe)
        name = pdf_filename(recipe)
        if download:
            (home.exports / name).write_bytes(data)
        disposition = "attachment" if download else "inline"
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{name}"'})

    # ---- intake: add ----

    def add_page(status: int = 200, **context) -> HTMLResponse:
        return page("add.html", status, default_structurer=library.get_setting("default_structurer", "local"),
                    has_key=bool(keys.get()), **context)

    @app.get("/add", response_class=HTMLResponse)
    def add_form():
        return add_page()

    @app.post("/add")
    async def add_items(request: Request):
        form = await request.form()
        structurer = "claude" if form.get("structurer") == "claude" else "local"
        cookbook = dict(cookbook_title=(form.get("cookbook_title") or "").strip() or None,
                        cookbook_author=(form.get("cookbook_author") or "").strip() or None)
        new_jobs: list[Job] = []

        for line in (form.get("urls") or "").splitlines():
            if line.strip():
                new_jobs.append(Job(kind="url", label=line.strip(), url=line.strip(), structurer=structurer))

        photos: list[tuple[str, str]] = []
        rejected: list[str] = []
        for upload in form.getlist("files"):
            name = Path(getattr(upload, "filename", "") or "").name
            if not name:
                continue
            suffix = Path(name).suffix.lower()
            if suffix != ".pdf" and suffix not in PHOTO_TYPES:
                rejected.append(name)
                continue
            target = home.originals / f"{uuid.uuid4().hex[:8]}-{_slug(Path(name).stem)}{suffix}"
            target.write_bytes(await upload.read())
            if suffix == ".pdf":
                new_jobs.append(Job(kind="pdf", label=name, files=[str(target)], structurer=structurer,
                                    pages=(form.get("pages") or "").strip(), **cookbook))
            else:
                photos.append((name, str(target)))
        if photos and form.get("one_recipe"):
            label = photos[0][0] if len(photos) == 1 else f"{photos[0][0]} and {len(photos) - 1} more"
            new_jobs.append(Job(kind="photo", label=label, files=[p for _, p in photos], structurer=structurer, **cookbook))
        else:
            new_jobs += [Job(kind="photo", label=name, files=[path], structurer=structurer, **cookbook)
                         for name, path in photos]

        if not new_jobs:
            problem = (f"These files are not photos or PDFs: {', '.join(rejected)}." if rejected
                       else "Paste at least one web address, or choose at least one photo or PDF.")
            return add_page(status=422, problem=problem)
        for job in new_jobs:
            jobs.add(job)
        worker.wake()
        return RedirectResponse("/queue", status_code=303)

    # ---- intake: queue ----

    @app.get("/queue", response_class=HTMLResponse)
    def queue_page():
        rows = [(job, jobs.drafts_for(job.id)) for job in jobs.list()]
        active = any(job.state in ACTIVE_STATES for job, _ in rows)
        waiting = next((job for job, _ in rows if job.state == "waiting"), None)
        return page("queue.html", rows=rows, active=active or waiting is not None, waiting=waiting,
                    has_key=bool(keys.get()))

    @app.post("/jobs/{job_id}/retry")
    async def retry_job(job_id: int, request: Request):
        require_job(job_id)
        form = await request.form()
        jobs.retry(job_id, "claude" if form.get("structurer") == "claude" else "local")
        worker.wake()
        return RedirectResponse("/queue", status_code=303)

    @app.post("/jobs/{job_id}/delete")
    def delete_job(job_id: int):
        require_job(job_id)
        jobs.delete(job_id)  # originals stay on disk
        return RedirectResponse("/queue", status_code=303)

    # ---- intake: review ----

    def review_page(draft, form: dict, status: int = 200, **context) -> HTMLResponse:
        job = jobs.get(draft.job_id)
        images = [Path(f).name for f in (job.material.images if job and job.material else [])]
        return page("review.html", status, draft=draft, job=job, form=form, images=images,
                    duplicates=library.find_duplicates(draft.recipe),
                    original_text=draft.recipe.original_text, flags=draft.recipe.flags,
                    categories=library.categories(), has_key=bool(keys.get()), **context)

    @app.get("/drafts/{draft_id}", response_class=HTMLResponse)
    def review_draft(draft_id: int):
        draft = require_draft(draft_id)
        if draft.state == "saved" and draft.recipe_id:
            return RedirectResponse(f"/recipes/{draft.recipe_id}", status_code=303)
        return review_page(draft, form_from_recipe(draft.recipe))

    @app.post("/drafts/{draft_id}")
    async def save_draft(draft_id: int, request: Request):
        draft = require_draft(draft_id)
        if draft.state == "saved" and draft.recipe_id:
            return RedirectResponse(f"/recipes/{draft.recipe_id}", status_code=303)
        form = dict(await request.form())
        recipe = finish_draft(recipe_from_form(form, draft.recipe), draft.recipe.original_text, library.glossary())
        if form.get("action") == "check":  # keep the edits and re-run the checks without saving
            jobs.update_draft(draft_id, recipe)
            return RedirectResponse(f"/drafts/{draft_id}", status_code=303)
        missing = recipe.missing_for_save()
        if missing:
            return review_page(draft, form, status=422, missing=missing)
        saved = library.save(recipe.model_copy(update={"id": None, "flags": []}))
        jobs.mark_draft(draft_id, "saved", recipe_id=saved.id)
        return RedirectResponse(f"/recipes/{saved.id}?saved=1", status_code=303)

    @app.post("/drafts/{draft_id}/discard")
    def discard_draft(draft_id: int):
        require_draft(draft_id)
        jobs.mark_draft(draft_id, "discarded")  # the original file is kept
        return RedirectResponse("/queue", status_code=303)

    @app.get("/originals/{name}")
    def original_file(name: str):
        """Serve a kept original (photo, page image, PDF). Web snapshots are served as plain text."""
        path = home.originals / Path(name).name
        if Path(name).name != name or not path.is_file():
            raise HTTPException(status_code=404, detail="That original file is not here.")
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not kind.startswith("image/") and kind != "application/pdf":
            kind = "text/plain; charset=utf-8"
        return Response(path.read_bytes(), media_type=kind, headers={"X-Content-Type-Options": "nosniff"})

    # ---- book ----

    def book_page(status: int = 200, **context) -> HTMLResponse:
        defaults = dict(title="Recipes from Our Kitchen", subtitle="", kicker="A Family Cookbook",
                        edition=f"{datetime.now().year} Edition", categories=None, tag="", binding="bound",
                        notes=True, qr=True)
        options = {**defaults, **library.get_setting("book_options", {})}
        return page("book.html", status, options=options, categories=library.categories(),
                    editions=library.editions(), total=len(library.list()), **context)

    @app.get("/book", response_class=HTMLResponse)
    def book_form(made: int = 0):
        return book_page(made=library.get_edition(made) if made else None)

    @app.post("/book")
    async def make_book(request: Request):
        form = await request.form()
        chosen = [str(name) for name in form.getlist("categories")]
        options = BookOptions(
            title=(form.get("title") or "").strip() or "Recipes",
            subtitle=(form.get("subtitle") or "").strip(),
            kicker=(form.get("kicker") or "").strip(),
            edition=(form.get("edition") or "").strip(),
            categories=chosen or None,
            tag=(form.get("tag") or "").strip() or None,
            binding=form.get("binding") if form.get("binding") in BINDINGS else "bound",
            notes=bool(form.get("notes")),
            qr=bool(form.get("qr")),
        )
        library.set_setting("book_options", {**asdict(options), "tag": options.tag or ""})
        try:
            result = await run_in_threadpool(build_book, library, options)
        except ValueError as error:
            return book_page(status=422, problem=str(error))
        name = f"{_slug(options.title)}-{datetime.now():%Y-%m-%d-%H%M%S}.pdf"
        (home.exports / name).write_bytes(result.pdf)
        edition_id = library.add_edition(options.title, name, dict(
            pages=result.pages, recipe_count=result.recipe_count, report=result.report,
            binding=options.binding, tag=options.tag or "", categories=options.categories,
            page_map={str(page): recipe_id for page, recipe_id in result.page_map.items()},
        ))
        return RedirectResponse(f"/book?made={edition_id}", status_code=303)

    @app.get("/editions/{edition_id}/pdf")
    def edition_pdf(edition_id: int, download: int = 0):
        edition = library.get_edition(edition_id)
        path = home.exports / Path(edition["file"]).name if edition else None
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="That book file is no longer in the exports folder.")
        disposition = "attachment" if download else "inline"
        return Response(path.read_bytes(), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{path.name}"'})

    # ---- settings ----

    def settings_page(status: int = 200, **context) -> HTMLResponse:
        return page("settings.html", status, categories=library.categories(),
                    glossary=glossary_to_text(library.glossary()),
                    local_model=library.get_setting("local_model", DEFAULT_LOCAL_MODEL),
                    default_structurer=library.get_setting("default_structurer", "local"),
                    has_key=bool(keys.get()), **context)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_form(saved: str = ""):
        return settings_page(saved=bool(saved))

    @app.post("/settings")
    async def save_settings(request: Request):
        form = await request.form()
        try:
            library.set_categories([str(name) for name in form.getlist("category")])
        except ValueError:
            return settings_page(status=422, problem="Categories need five different names, none empty.")
        library.set_glossary(glossary_from_text(form.get("glossary") or ""))
        library.set_setting("local_model", (form.get("local_model") or "").strip() or DEFAULT_LOCAL_MODEL)
        library.set_setting("default_structurer", "claude" if form.get("default_structurer") == "claude" else "local")
        new_key = (form.get("claude_key") or "").strip()
        if form.get("clear_key"):
            keys.clear()
        elif new_key:
            keys.set(new_key)
        return RedirectResponse("/settings?saved=1", status_code=303)

    return app
