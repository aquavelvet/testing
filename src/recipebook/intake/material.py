"""What a reader hands to a structurer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..model import Source

LOW_TEXT_CHARS = 200


class ReaderError(Exception):
    """An input could not be read. `advice` tells the user what to try instead."""

    def __init__(self, message: str, advice: str = ""):
        super().__init__(message)
        self.advice = advice


class SourceMaterial(BaseModel):
    kind: Literal["url", "pdf", "photo"]
    text: str = ""
    images: list[str] = Field(default_factory=list)  # page or photo images, as JPEG paths
    files: list[str] = Field(default_factory=list)  # originals kept on disk
    has_recipe_data: bool = False  # the text came from recipe data embedded in a web page
    source: Source = Field(default_factory=Source)
    warnings: list[str] = Field(default_factory=list)

    def low_text(self) -> bool:
        return len(self.text.strip()) < LOW_TEXT_CHARS
