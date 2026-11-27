"""Ingredient lists: pick recipes by page or recipe number and merge what they need."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from .model import Recipe
from .style.numbers import format_range
from .style.units import lookup, unit_word


class EntryError(ValueError):
    """What the user typed could not be read as numbers."""


def parse_numbers(text: str) -> list[int]:
    """'34, 36-37 40' -> [34, 36, 37, 40]. Order is kept and repeats are dropped."""
    numbers: list[int] = []
    for part in re.split(r"[,\s;]+", (text or "").strip()):
        if not part:
            continue
        match = re.fullmatch(r"#?(\d+)(?:[-–](\d+))?", part)
        if not match:
            raise EntryError(f"“{part}” is not a number or a range like 36-37.")
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        if last < first or last - first > 500:
            raise EntryError(f"“{part}” is not a valid range.")
        numbers += [n for n in range(first, last + 1) if n not in numbers]
    if not numbers:
        raise EntryError("Enter at least one number.")
    return numbers


def recipes_on_pages(page_map: dict, pages: list[int]) -> tuple[list[int], list[int]]:
    """Recipe numbers for the given pages of an edition, and the pages that hold no recipe."""
    found: list[int] = []
    skipped: list[int] = []
    for page in pages:
        recipe_id = page_map.get(str(page), page_map.get(page))
        if recipe_id is None:
            skipped.append(page)
        elif recipe_id not in found:
            found.append(recipe_id)
    return found, skipped


@dataclass
class Line:
    item: str
    amounts: list[str]
    recipes: list[int]

    def text(self) -> str:
        amount = " + ".join(self.amounts)
        numbers = ", ".join(str(n) for n in self.recipes)
        label = "No." if len(self.recipes) == 1 else "Nos."
        return f"{self.item}: {amount} ({label} {numbers})" if amount else f"{self.item} ({label} {numbers})"


@dataclass
class MergedList:
    needed: list[Line] = field(default_factory=list)
    optional: list[Line] = field(default_factory=list)
    as_written: list[tuple[int, str]] = field(default_factory=list)  # lines the parser could not read

    def text(self, recipes: list[Recipe]) -> str:
        out = ["Ingredient list for: " + "; ".join(f"No. {r.id} {r.title}" for r in recipes), ""]
        out += [line.text() for line in self.needed]
        if self.optional:
            out += ["", "Optional and for serving:"] + [line.text() for line in self.optional]
        if self.as_written:
            out += ["", "As written:"] + [f"{text} (No. {number})" for number, text in self.as_written]
        return "\n".join(out)


class _Tally:
    def __init__(self) -> None:
        self.by_unit: dict[str | None, list[Fraction]] = {}  # unit -> [low total, high total]
        self.unmeasured: list[str] = []  # "pinch", or "" for a bare mention
        self.recipes: list[int] = []

    def add(self, ingredient, recipe_id: int) -> None:
        if recipe_id not in self.recipes:
            self.recipes.append(recipe_id)
        if ingredient.quantity is None:
            word = ingredient.unit or ""
            if word not in self.unmeasured:
                self.unmeasured.append(word)
            return
        low, high = ingredient.quantity, ingredient.quantity_max or ingredient.quantity
        totals = self.by_unit.setdefault(ingredient.unit, [Fraction(0), Fraction(0)])
        totals[0] += low
        totals[1] += high

    def amounts(self) -> list[str]:
        parts = []
        for unit_name, (low, high) in self.by_unit.items():
            amount = format_range(low, high if high != low else None)
            unit = lookup(unit_name) if unit_name else None
            parts.append(f"{amount} {unit_word(unit, high)}" if unit else amount)
        for word in self.unmeasured:
            if word:
                parts.append(f"a {word}")
            elif not self.by_unit and len(self.unmeasured) == 1:
                continue  # a bare mention with nothing to add to: the item name says it all
            else:
                parts.append("some")
        return parts


def merge(recipes: list[Recipe]) -> MergedList:
    """One combined list. Same item and unit are added; different units sit side by side."""
    needed: dict[str, _Tally] = {}
    optional: dict[str, _Tally] = {}
    merged = MergedList()
    for recipe in recipes:
        for ingredient in recipe.ingredients():
            if not ingredient.item:
                merged.as_written.append((recipe.id, ingredient.text))
                continue
            bucket = optional if ingredient.optional else needed
            bucket.setdefault(ingredient.item, _Tally()).add(ingredient, recipe.id)
    for bucket, target in ((needed, merged.needed), (optional, merged.optional)):
        for item in sorted(bucket, key=str.lower):
            target.append(Line(item, bucket[item].amounts(), bucket[item].recipes))
    return merged
