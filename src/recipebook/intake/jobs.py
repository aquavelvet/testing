"""Intake jobs and the drafts they produce, stored beside the library."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..model import Recipe
from .material import SourceMaterial

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    data       TEXT NOT NULL,
    state      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    data      TEXT NOT NULL,
    state     TEXT NOT NULL,           -- needs_review, saved, discarded
    recipe_id INTEGER
);
"""

JobState = Literal["queued", "reading", "structuring", "waiting", "done", "failed"]
PENDING = ("queued", "waiting")


class Job(BaseModel):
    id: int | None = None
    kind: Literal["url", "pdf", "photo"]
    label: str  # what the user sees: the address or the file names
    url: str | None = None
    files: list[str] = Field(default_factory=list)
    pages: str = ""
    cookbook_title: str | None = None
    cookbook_author: str | None = None
    structurer: Literal["local", "claude"] = "local"
    state: JobState = "queued"
    message: str = ""
    advice: str = ""
    material: SourceMaterial | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Draft(BaseModel):
    id: int
    job_id: int
    state: Literal["needs_review", "saved", "discarded"]
    recipe: Recipe
    recipe_id: int | None = None


class JobStore:
    def __init__(self, database: Path):
        self.database = Path(database)
        with self._connect() as con:
            con.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.database, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def _job(row) -> Job:
        return Job.model_validate_json(row["data"]).model_copy(update={"id": row["id"], "state": row["state"]})

    # ---- jobs ----

    def add(self, job: Job) -> Job:
        with self._connect() as con:
            cursor = con.execute("INSERT INTO jobs (data, state, created_at) VALUES (?, ?, ?)",
                                 (job.model_dump_json(), job.state, job.created_at.isoformat()))
        return job.model_copy(update={"id": cursor.lastrowid})

    def update(self, job: Job) -> Job:
        with self._connect() as con:
            con.execute("UPDATE jobs SET data = ?, state = ? WHERE id = ?", (job.model_dump_json(), job.state, job.id))
        return job

    def get(self, job_id: int) -> Job | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def list(self) -> list[Job]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [self._job(row) for row in rows]

    def pending(self) -> list[Job]:
        """Jobs that still need work, oldest first."""
        with self._connect() as con:
            rows = con.execute(f"SELECT * FROM jobs WHERE state IN {PENDING} ORDER BY id").fetchall()
        return [self._job(row) for row in rows]

    def requeue_interrupted(self) -> int:
        """After a restart, put jobs that were mid-flight back in the queue."""
        count = 0
        for job in self.list():
            if job.state in ("reading", "structuring"):
                self.update(job.model_copy(update={"state": "queued", "message": "", "advice": ""}))
                count += 1
        return count

    def retry(self, job_id: int, structurer: str) -> Job:
        """Run a job again, for example with Claude. Its unreviewed drafts are replaced."""
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        with self._connect() as con:
            con.execute("DELETE FROM drafts WHERE job_id = ? AND state = 'needs_review'", (job_id,))
        return self.update(job.model_copy(update={
            "structurer": structurer, "state": "queued", "message": "", "advice": ""}))

    def delete(self, job_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    # ---- drafts ----

    @staticmethod
    def _draft(row) -> Draft:
        return Draft(id=row["id"], job_id=row["job_id"], state=row["state"], recipe_id=row["recipe_id"],
                     recipe=Recipe.model_validate_json(row["data"]))

    def add_draft(self, job_id: int, recipe: Recipe) -> Draft:
        with self._connect() as con:
            cursor = con.execute("INSERT INTO drafts (job_id, data, state) VALUES (?, ?, 'needs_review')",
                                 (job_id, recipe.model_dump_json()))
        return Draft(id=cursor.lastrowid, job_id=job_id, state="needs_review", recipe=recipe)

    def get_draft(self, draft_id: int) -> Draft | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return self._draft(row) if row else None

    def drafts_for(self, job_id: int) -> list[Draft]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM drafts WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
        return [self._draft(row) for row in rows]

    def update_draft(self, draft_id: int, recipe: Recipe) -> None:
        with self._connect() as con:
            con.execute("UPDATE drafts SET data = ? WHERE id = ?", (recipe.model_dump_json(), draft_id))

    def mark_draft(self, draft_id: int, state: str, recipe_id: int | None = None) -> None:
        with self._connect() as con:
            con.execute("UPDATE drafts SET state = ?, recipe_id = ? WHERE id = ?", (state, recipe_id, draft_id))

    def needing_review(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM drafts WHERE state = 'needs_review'").fetchone()[0]
