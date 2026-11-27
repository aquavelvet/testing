"""Where the app keeps its data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Home:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "library.db"

    @property
    def originals(self) -> Path:
        return self.root / "originals"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    def ensure(self) -> "Home":
        for folder in (self.root, self.originals, self.inbox, self.exports):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def default_home() -> Home:
    """~/RecipeBook, or the folder named by RECIPEBOOK_HOME."""
    override = os.environ.get("RECIPEBOOK_HOME")
    return Home(Path(override).expanduser() if override else Path.home() / "RecipeBook")
