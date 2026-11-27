"""The recipe library: one SQLite file holding recipes, settings, and the glossary."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .model import DEFAULT_CATEGORIES, Recipe
from .style.glossary import DEFAULT_GLOSSARY, GlossaryEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- the permanent recipe number; never reused
    title      TEXT NOT NULL,
    category   TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS layouts (
    recipe_id INTEGER PRIMARY KEY,
    key       TEXT NOT NULL,       -- what the layout was computed from
    data      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS editions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title      TEXT NOT NULL,
    file       TEXT NOT NULL,
    data       TEXT NOT NULL       -- options, page count, report, and the page map
);
CREATE TABLE IF NOT EXISTS glossary (
    id        INTEGER PRIMARY KEY,
    preferred TEXT NOT NULL UNIQUE,
    variants  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class RecipeSummary:
    id: int
    title: str
    category: str
    updated_at: str


class Library:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_SCHEMA)
            if con.execute("SELECT COUNT(*) FROM glossary").fetchone()[0] == 0:
                con.executemany(
                    "INSERT INTO glossary (preferred, variants) VALUES (?, ?)",
                    [(e.preferred, json.dumps(list(e.variants), ensure_ascii=False)) for e in DEFAULT_GLOSSARY],
                )

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.database, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:  # one transaction per operation
                yield con
        finally:
            con.close()

    # ---- recipes ----

    def save(self, recipe: Recipe) -> Recipe:
        """Insert or update. A new recipe gets the next permanent number."""
        now = datetime.now(timezone.utc)
        recipe = recipe.model_copy(update={"updated_at": now})
        with self._connect() as con:
            if recipe.id is None:
                cursor = con.execute(
                    "INSERT INTO recipes (title, category, data, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
                    (recipe.title, recipe.category, recipe.created_at.isoformat(), now.isoformat()),
                )
                recipe = recipe.model_copy(update={"id": cursor.lastrowid})
            updated = con.execute(
                "UPDATE recipes SET title = ?, category = ?, data = ?, updated_at = ? WHERE id = ?",
                (recipe.title, recipe.category, recipe.model_dump_json(), now.isoformat(), recipe.id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"No recipe numbered {recipe.id}")
        return recipe

    def get(self, recipe_id: int) -> Recipe | None:
        with self._connect() as con:
            row = con.execute("SELECT id, data FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            return None
        return Recipe.model_validate_json(row["data"]).model_copy(update={"id": row["id"]})

    def list(self, category: str | None = None) -> list[RecipeSummary]:
        query = "SELECT id, title, category, updated_at FROM recipes"
        args: tuple = ()
        if category is not None:
            query += " WHERE category = ?"
            args = (category,)
        with self._connect() as con:
            rows = con.execute(query + " ORDER BY title COLLATE NOCASE", args).fetchall()
        return [RecipeSummary(**dict(row)) for row in rows]

    def delete(self, recipe_id: int) -> bool:
        with self._connect() as con:
            return con.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,)).rowcount > 0

    # ---- settings ----

    def get_setting(self, key: str, default=None):
        with self._connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row["value"])

    def set_setting(self, key: str, value) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def categories(self) -> list[str]:
        return self.get_setting("categories", list(DEFAULT_CATEGORIES))

    def set_categories(self, names: list[str]) -> None:
        """Rename the five categories. A renamed category takes its recipes with it."""
        names = [name.strip() for name in names]
        current = self.categories()
        if len(names) != len(current) or any(not n for n in names) or len(set(names)) != len(names):
            raise ValueError(f"Need exactly {len(current)} different, non-empty category names")
        renames = {old: new for old, new in zip(current, names) if old != new}
        for summary in self.list():
            if summary.category in renames:
                recipe = self.get(summary.id)
                self.save(recipe.model_copy(update={"category": renames[summary.category]}))
        self.set_setting("categories", names)

    # ---- glossary ----

    def glossary(self) -> tuple[GlossaryEntry, ...]:
        with self._connect() as con:
            rows = con.execute("SELECT preferred, variants FROM glossary ORDER BY id").fetchall()
        return tuple(GlossaryEntry(row["preferred"], tuple(json.loads(row["variants"]))) for row in rows)

    def set_glossary(self, entries: list[GlossaryEntry]) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM glossary")
            con.executemany(
                "INSERT INTO glossary (preferred, variants) VALUES (?, ?)",
                [(e.preferred, json.dumps(list(e.variants), ensure_ascii=False)) for e in entries],
            )

    # ---- layout cache ----

    def get_layout(self, recipe_id: int, key: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT data FROM layouts WHERE recipe_id = ? AND key = ?", (recipe_id, key)).fetchone()
        return json.loads(row["data"]) if row else None

    def set_layout(self, recipe_id: int, key: str, data: dict) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO layouts (recipe_id, key, data) VALUES (?, ?, ?) "
                "ON CONFLICT(recipe_id) DO UPDATE SET key = excluded.key, data = excluded.data",
                (recipe_id, key, json.dumps(data)),
            )

    # ---- editions: every exported book, with its page map ----

    def add_edition(self, title: str, file: str, data: dict) -> int:
        with self._connect() as con:
            cursor = con.execute(
                "INSERT INTO editions (created_at, title, file, data) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), title, file, json.dumps(data, ensure_ascii=False)),
            )
        return cursor.lastrowid

    def editions(self) -> list[dict]:
        """Newest first. Each has id, created_at, title, file, and the stored data fields."""
        with self._connect() as con:
            rows = con.execute("SELECT * FROM editions ORDER BY id DESC").fetchall()
        return [{"id": r["id"], "created_at": r["created_at"], "title": r["title"], "file": r["file"],
                 **json.loads(r["data"])} for r in rows]

    def get_edition(self, edition_id: int) -> dict | None:
        return next((e for e in self.editions() if e["id"] == edition_id), None)
