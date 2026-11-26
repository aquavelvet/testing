"""The local web app: library, recipe form, PDF preview and export."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import jinja2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ..config import Home, default_home
from ..library import Library
from ..model import Recipe
from ..render.pdf import render_recipe_pdf
from ..style.housestyle import apply_house_style
from .forms import form_from_recipe, recipe_from_form

HERE = Path(__file__).parent
LOCAL_HOSTS = {"127.0.0.1", "localhost"}

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


def create_app(home: Home | None = None, extra_hosts: frozenset[str] = frozenset()) -> FastAPI:
    home = (home or default_home()).ensure()
    library = Library(home.database)
    allowed_hosts = LOCAL_HOSTS | set(extra_hosts)

    app = FastAPI(title="Recipe Book", docs_url=None, redoc_url=None, openapi_url=None)
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

    # ---- library ----

    @app.get("/", response_class=HTMLResponse)
    def library_page(deleted: str = ""):
        summaries = library.list()
        categories = library.categories()
        sections = [(name, [s for s in summaries if s.category == name]) for name in categories]
        other = [s for s in summaries if s.category not in categories]
        if other:
            sections.append(("Other", other))
        return page("library.html", sections=sections, total=len(summaries), deleted=deleted)

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

    return app
