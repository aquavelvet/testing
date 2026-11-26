"""Runs intake jobs: read, structure, apply the code rules, and leave drafts for review."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable

from ..library import Library
from ..model import Flag, Recipe, Source
from ..style.fidelity import check_fidelity
from ..style.housestyle import apply_house_style
from .jobs import Job, JobStore
from .material import ReaderError, SourceMaterial
from .ocr import Ocr
from .readers import read_pdf, read_photos, read_url
from .structure import USE_CLAUDE, StructurerError, StructurerUnavailable


def finish_draft(recipe: Recipe, material_text: str, glossary) -> Recipe:
    """Apply the code-enforced style rules and attach the fidelity flags."""
    styled = apply_house_style(recipe, glossary)
    kept = [flag for flag in styled.flags if not flag.kind.startswith(("amount_", "time_"))]
    return styled.model_copy(update={"flags": kept + check_fidelity(material_text, styled)})


class Pipeline:
    def __init__(self, jobs: JobStore, library: Library, originals: Path, ocr: Ocr,
                 structurer_for: Callable[[str], object], url_client=None):
        self.jobs, self.library, self.originals, self.ocr = jobs, library, originals, ocr
        self.structurer_for = structurer_for
        self.url_client = url_client

    def _read(self, job: Job) -> SourceMaterial:
        source = Source()
        if job.cookbook_title:
            source = Source(kind="cookbook", title=job.cookbook_title, author=job.cookbook_author)
        if job.kind == "url":
            return read_url(job.url or "", self.originals, self.url_client)
        if job.kind == "pdf":
            return read_pdf(Path(job.files[0]), self.originals, self.ocr, job.pages, source)
        return read_photos([Path(f) for f in job.files], self.originals, self.ocr, source)

    def process(self, job: Job) -> Job:
        """Run one job to a resting state: done, failed, or waiting."""
        try:
            if job.material is None:
                job = self.jobs.update(job.model_copy(update={"state": "reading", "message": "", "advice": ""}))
                job = self.jobs.update(job.model_copy(update={"material": self._read(job)}))
            material = job.material
            job = self.jobs.update(job.model_copy(update={"state": "structuring"}))
            recipes = self.structurer_for(job.structurer).structure(
                material, self.library.categories(), self.library.glossary())
        except ReaderError as error:
            return self._rest(job, "failed", str(error), error.advice)
        except StructurerUnavailable as error:
            return self._rest(job, "waiting", str(error), error.fix)
        except StructurerError as error:
            return self._rest(job, "failed", str(error), error.advice)
        except Exception as error:  # an unexpected bug must not kill the worker or strand the job
            traceback.print_exc()
            return self._rest(job, "failed", f"Unexpected error: {type(error).__name__}: {error}", "")

        if not recipes:
            advice = USE_CLAUDE if job.structurer == "local" else "Check that the input shows a whole recipe."
            return self._rest(job, "failed", "No recipe was found in this item.", advice)

        glossary = self.library.glossary()
        for recipe in recipes:
            draft = finish_draft(recipe, material.text, glossary)
            extra = []
            if material.kind != "url" and material.low_text():
                extra.append(Flag(kind="low_text", severity="warning", field=None,
                                  message="Very little text could be read; the photo may be blurry. Check every line."))
            extra += [Flag(kind="reader_note", severity="info", field=None, message=w) for w in material.warnings]
            self.jobs.add_draft(job.id, draft.model_copy(update={"flags": extra + draft.flags}))
        count = len(recipes)
        return self._rest(job, "done", f"{count} recipe{'' if count == 1 else 's'} ready for review.", "")

    def _rest(self, job: Job, state: str, message: str, advice: str) -> Job:
        return self.jobs.update(job.model_copy(update={"state": state, "message": message, "advice": advice}))

    def run_pending(self) -> bool:
        """Process every pending job once. Returns True if any job is left waiting."""
        waiting_on: set[str] = set()
        for job in self.jobs.pending():
            if job.structurer in waiting_on:
                continue  # the same structurer just proved unavailable; do not hammer it
            if self.process(job).state == "waiting":
                waiting_on.add(job.structurer)
        return bool(waiting_on)


class Worker:
    """One background thread that works through the queue."""

    def __init__(self, pipeline: Pipeline, idle_seconds: float = 1.0, waiting_seconds: float = 5.0):
        self.pipeline, self.idle_seconds, self.waiting_seconds = pipeline, idle_seconds, waiting_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.pipeline.jobs.requeue_interrupted()
        self._thread = threading.Thread(target=self._loop, name="recipebook-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                waiting = self.pipeline.run_pending()
            except Exception:
                traceback.print_exc()
                waiting = True
            self._wake.wait(self.waiting_seconds if waiting else self.idle_seconds)
            self._wake.clear()
