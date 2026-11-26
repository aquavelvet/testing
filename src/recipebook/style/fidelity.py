"""The fidelity check: a rewrite may change wording, never amounts."""

from __future__ import annotations

from fractions import Fraction

from ..model import Flag, Recipe, format_minutes
from .numbers import find_numbers, format_quantity


def check_fidelity(original_text: str, recipe: Recipe) -> list[Flag]:
    """Compare the numbers in the original text with the numbers in the recipe.

    Returns a warning for every recipe line holding a number the original does not have,
    and one low-severity note listing original numbers that the recipe no longer has.
    """
    if not original_text.strip():
        return []

    original = set(find_numbers(original_text))
    used: set[Fraction] = set()
    flags: list[Flag] = []

    def check(text: str, field: str, label: str) -> None:
        numbers = find_numbers(text)
        used.update(numbers)
        unknown = [n for n in numbers if n not in original]
        if unknown:
            shown = ", ".join(format_quantity(n) for n in dict.fromkeys(unknown))
            flags.append(Flag(
                kind="amount_changed", severity="warning", field=field,
                message=f"{label}: {shown} does not appear in the original.",
            ))

    for g, group in enumerate(recipe.ingredient_groups):
        for i, ingredient in enumerate(group.items):
            check(ingredient.text, f"ingredients.{g}.{i}", f"Ingredient “{ingredient.text}”")
    for s, step in enumerate(recipe.steps):
        check(step.text, f"steps.{s}", f"Step {s + 1}")
    if recipe.yield_value:
        check(recipe.yield_value, "yield_value", "Yield")
    for field, label, minutes in (
        ("active_minutes", "Active time", recipe.active_minutes),
        ("total_minutes", "Total time", recipe.total_minutes),
    ):
        if minutes is None:
            continue
        used.add(Fraction(minutes))
        spoken = find_numbers(format_minutes(minutes))
        used.update(spoken)
        if Fraction(minutes) not in original and any(n not in original for n in spoken):
            flags.append(Flag(
                kind="time_unconfirmed", severity="info", field=field,
                message=f"{label} ({format_minutes(minutes)}) does not appear in the original.",
            ))

    dropped = sorted(original - used)
    if dropped:
        shown = ", ".join(format_quantity(n) for n in dropped[:12])
        more = "" if len(dropped) <= 12 else f", and {len(dropped) - 12} more"
        flags.append(Flag(
            kind="amount_dropped", severity="info", field=None,
            message=f"Numbers in the original that are not in the recipe: {shown}{more}.",
        ))
    return flags
