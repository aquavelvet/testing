"""The shared recipe model. Every other unit speaks these types."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_CATEGORIES = [
    "Breakfast & Brunch",
    "Starters & Soups",
    "Main Dishes",
    "Salads & Sides",
    "Desserts & Baking",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Ingredient(BaseModel):
    """One ingredient line. `text` is what prints; the other fields are its parts."""

    text: str
    quantity: Fraction | None = None
    quantity_max: Fraction | None = None
    unit: str | None = None
    item: str | None = None
    prep: str | None = None
    optional: bool = False


class IngredientGroup(BaseModel):
    name: str | None = None
    items: list[Ingredient] = Field(default_factory=list)


class Step(BaseModel):
    lead: str | None = None
    text: str


class Source(BaseModel):
    kind: Literal["web", "cookbook", "other"] = "other"
    url: str | None = None
    title: str | None = None
    author: str | None = None
    page: str | None = None
    label: str | None = None

    def credit(self) -> str:
        """The printed source line, or an empty string when nothing is known."""
        if self.kind == "web" and self.url:
            shown = re.sub(r"^https?://(www\.)?", "", self.url.strip()).rstrip("/")
            return f"Source: {shown}"
        if self.kind == "cookbook" and self.title:
            parts = [self.title.strip()]
            if self.author:
                parts.append(f"by {self.author.strip()}")
            if self.page:
                parts.append(f"page {self.page.strip()}")
            return "Source: " + ", ".join(parts)
        if self.label:
            return f"Source: {self.label.strip()}"
        return ""


class Flag(BaseModel):
    """A review warning attached to a draft or recipe."""

    kind: str
    severity: Literal["warning", "info"] = "warning"
    field: str | None = None
    message: str


class Recipe(BaseModel):
    id: int | None = None
    title: str
    headnote: str = ""
    yield_label: Literal["Serves", "Makes"] = "Serves"
    yield_value: str = ""
    active_minutes: int | None = None
    total_minutes: int | None = None
    ingredient_groups: list[IngredientGroup] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    note: str = ""
    category: str = DEFAULT_CATEGORIES[2]
    tags: list[str] = Field(default_factory=list)
    source: Source = Field(default_factory=Source)
    original_text: str = ""
    original_files: list[str] = Field(default_factory=list)
    structured_by: Literal["local", "claude", "manual"] = "manual"
    flags: list[Flag] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def ingredients(self) -> list[Ingredient]:
        return [ing for group in self.ingredient_groups for ing in group.items]

    def missing_for_save(self) -> list[str]:
        """Names of the required fields that are still empty."""
        missing = []
        if not self.title.strip():
            missing.append("title")
        if not self.ingredients():
            missing.append("ingredients")
        if not self.steps:
            missing.append("directions")
        if not self.category.strip():
            missing.append("category")
        return missing


def format_minutes(minutes: int | None) -> str:
    """45 -> '45 minutes', 60 -> '1 hour', 105 -> '1 hour 45 minutes'."""
    if minutes is None:
        return ""
    hours, mins = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if mins or not hours:
        parts.append(f"{mins} minute" + ("s" if mins != 1 else ""))
    return " ".join(parts)


_DURATION_UNIT = re.compile(r"\s*(hours?|hrs?|h|minutes?|mins?|m)\b", re.IGNORECASE)


def parse_minutes(text: str) -> int | None:
    """Read '1 hour 45 minutes', '1h 45m', '1:45', or a bare number of minutes."""
    text = (text or "").strip().lower()
    if not text:
        return None
    clock = re.fullmatch(r"(\d+):(\d{2})", text)
    if clock:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    if re.fullmatch(r"\d+", text):
        return int(text)
    from .style.numbers import QUANTITY_RE, parse_quantity_prefix

    total = Fraction(0)
    found = False
    position = 0
    while True:
        match = QUANTITY_RE.search(text, position)
        if not match:
            break
        value, _upper, _rest = parse_quantity_prefix(text[match.start():])
        unit = _DURATION_UNIT.match(text, match.end())
        if value is not None and unit:
            found = True
            total += value * (60 if unit.group(1).startswith("h") else 1)
            position = unit.end()
        else:
            position = match.end()
    return round(total) if found else None
