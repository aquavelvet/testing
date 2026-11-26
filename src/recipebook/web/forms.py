"""Between the recipe form's plain text boxes and the Recipe model."""

from __future__ import annotations

import re

from ..model import Ingredient, IngredientGroup, Recipe, Source, Step, format_minutes, parse_minutes

_NUMBERING = re.compile(r"^(?:step\s*\d+\s*[.:)-]|\d+\s*[.)])\s*", re.IGNORECASE)
_LEAD = re.compile(r"^([A-Z][^.:!?;]{1,40}):\s+(?=\S)")


def parse_ingredients(text: str) -> list[IngredientGroup]:
    """One ingredient per line. A line ending in a colon starts a named group."""
    groups: list[IngredientGroup] = []
    current = IngredientGroup()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(":"):
            if current.items:
                groups.append(current)
            current = IngredientGroup(name=line.rstrip(":").strip() or None)
        else:
            current.items.append(Ingredient(text=line))
    if current.items:
        groups.append(current)
    return groups


def ingredients_to_text(groups: list[IngredientGroup]) -> str:
    blocks = []
    for group in groups:
        lines = [f"{group.name}:"] if group.name else []
        lines += [item.text for item in group.items]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def parse_steps(text: str) -> list[Step]:
    """One step per paragraph (or per line when there are no blank lines).

    Typed numbering is dropped. A short capitalized phrase before a colon, such as
    "Make the topping: ...", becomes the step's bold lead-in.
    """
    text = (text or "").replace("\r\n", "\n").strip()
    chunks = re.split(r"\n\s*\n", text) if re.search(r"\n\s*\n", text) else text.split("\n")
    steps = []
    for chunk in chunks:
        chunk = _NUMBERING.sub("", " ".join(chunk.split()))
        if not chunk:
            continue
        lead = None
        match = _LEAD.match(chunk)
        if match and len(match.group(1).split()) <= 5:
            lead, chunk = match.group(1).strip(), chunk[match.end():]
        steps.append(Step(lead=lead, text=chunk))
    return steps


def steps_to_text(steps: list[Step]) -> str:
    return "\n\n".join(f"{step.lead}: {step.text}" if step.lead else step.text for step in steps)


def recipe_from_form(form, existing: Recipe | None = None) -> Recipe:
    """Build a Recipe from submitted form fields, keeping what the form does not carry."""

    def field(name: str) -> str:
        return (form.get(name) or "").strip()

    kind = field("source_kind") or "other"
    source = Source(
        kind=kind if kind in ("web", "cookbook", "other") else "other",
        url=field("source_url") or None,
        title=field("source_title") or None,
        author=field("source_author") or None,
        page=field("source_page") or None,
        label=field("source_label") or None,
    )
    values = dict(
        title=field("title"),
        headnote=field("headnote"),
        yield_label="Makes" if field("yield_label") == "Makes" else "Serves",
        yield_value=field("yield_value"),
        active_minutes=parse_minutes(field("active_time")),
        total_minutes=parse_minutes(field("total_time")),
        ingredient_groups=parse_ingredients(form.get("ingredients") or ""),
        steps=parse_steps(form.get("directions") or ""),
        note=field("note"),
        category=field("category"),
        tags=[tag.strip() for tag in field("tags").split(",") if tag.strip()],
        source=source,
    )
    if existing is not None:
        return existing.model_copy(update=values)
    return Recipe(**values)


def form_from_recipe(recipe: Recipe) -> dict[str, str]:
    return dict(
        title=recipe.title,
        headnote=recipe.headnote,
        yield_label=recipe.yield_label,
        yield_value=recipe.yield_value,
        active_time=format_minutes(recipe.active_minutes),
        total_time=format_minutes(recipe.total_minutes),
        ingredients=ingredients_to_text(recipe.ingredient_groups),
        directions=steps_to_text(recipe.steps),
        note=recipe.note,
        category=recipe.category,
        tags=", ".join(recipe.tags),
        source_kind=recipe.source.kind,
        source_url=recipe.source.url or "",
        source_title=recipe.source.title or "",
        source_author=recipe.source.author or "",
        source_page=recipe.source.page or "",
        source_label=recipe.source.label or "",
    )
