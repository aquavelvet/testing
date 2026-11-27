"""One entry point that applies every code-enforced style rule to a recipe."""

from __future__ import annotations

import re

from ..model import IngredientGroup, Recipe, Step
from .glossary import DEFAULT_GLOSSARY
from .numbers import normalize_fractions
from .parser import parse_ingredient_line

_DEGREES_F = re.compile(r"(\d)\s*(?:°\s*F\b|degrees?\s*(?:F\b|Fahrenheit\b))", re.IGNORECASE)
_DEGREE_OVEN = re.compile(r"(\d)\s*(?:°\s*F\b|°|degrees?(?:\s*(?:F\b|Fahrenheit\b))?)\s+oven\b", re.IGNORECASE)
_HYPHEN_RANGE = re.compile(r"(?<![\d/⁄.-])(\d+)\s?[-–]\s?(\d+)(?=\s+[A-Za-z]|$)")


def _spell_range(match: re.Match) -> str:
    low, high = int(match.group(1)), int(match.group(2))
    return f"{low} to {high}" if high > low else match.group(0)


def tidy_text(text: str, running: bool = True) -> str:
    """Spacing, apostrophes, and fraction characters.

    Running text (directions, notes, headnotes) also gets '375 degrees', '200-degree
    oven', and '2 to 3 minutes'. Titles get only the basics.
    """
    text = (text or "").replace("\N{NO-BREAK SPACE}", " ")
    text = re.sub(r"(?<=\w)'(?=\w)|(?<=s)'(?=\s|$)", "’", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = normalize_fractions(text)
    if not running:
        return text
    text = _DEGREE_OVEN.sub(r"\1-degree oven", text)
    text = _DEGREES_F.sub(r"\1 degrees", text)
    return _HYPHEN_RANGE.sub(_spell_range, text)


def apply_house_style(recipe: Recipe, glossary=DEFAULT_GLOSSARY) -> Recipe:
    """Return a copy of the recipe with all code rules applied."""
    groups = []
    for group in recipe.ingredient_groups:
        items = [parse_ingredient_line(item.text, glossary) for item in group.items]
        items = [item for item in items if item.text]
        if items:
            name = tidy_text(group.name or "").rstrip(":").strip() or None
            groups.append(IngredientGroup(name=name, items=items))

    steps = []
    for step in recipe.steps:
        text = tidy_text(step.text)
        if text:
            lead = tidy_text(step.lead or "").rstrip(":").strip() or None
            steps.append(Step(lead=lead, text=text))

    tags, seen = [], set()
    for tag in recipe.tags:
        tag = re.sub(r"\s+", " ", tag).strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)

    return recipe.model_copy(update=dict(
        title=tidy_text(recipe.title, running=False),
        headnote=tidy_text(recipe.headnote),
        yield_value=tidy_text(recipe.yield_value),
        note=tidy_text(recipe.note),
        ingredient_groups=groups,
        steps=steps,
        tags=tags,
    ))
