"""The fidelity check: a rewrite may change wording, never amounts."""

from __future__ import annotations

from collections import Counter
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

    original_counts = Counter(find_numbers(original_text))
    original = set(original_counts)
    used: Counter[Fraction] = Counter()
    lines_with: dict[Fraction, list[str]] = {}
    flags: list[Flag] = []

    def check(text: str, field: str, label: str) -> None:
        numbers = find_numbers(text)
        used.update(numbers)
        if field.startswith("ingredients."):
            for number in set(numbers):
                lines_with.setdefault(number, []).append(text)
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
        spoken = find_numbers(format_minutes(minutes))
        used.update(spoken)
        used.setdefault(Fraction(minutes), 0)
        if Fraction(minutes) not in original and any(n not in original for n in spoken):
            flags.append(Flag(
                kind="time_unconfirmed", severity="info", field=field,
                message=f"{label} ({format_minutes(minutes)}) does not appear in the original.",
            ))

    dropped = sorted(n for n in original if n not in used)

    # A swapped amount can hide behind a number that exists elsewhere in the original
    # (¾ cup rewritten as 1 cup). The sign is a number missing from the recipe together
    # with another number used more often than the original uses it.
    if dropped:
        suspects = []
        for number, lines in lines_with.items():
            if number in original and used[number] > original_counts[number]:
                suspects += [line for line in lines if line not in suspects]
        if suspects:
            missing = ", ".join(format_quantity(n) for n in dropped[:6])
            shown = "; ".join(f"“{line}”" for line in suspects[:6])
            flags.append(Flag(
                kind="amount_suspect", severity="warning", field="ingredients",
                message=f"The original has {missing}, which the recipe does not. One of these lines may have "
                        f"the wrong amount: {shown}",
            ))

    if dropped:
        shown = ", ".join(format_quantity(n) for n in dropped[:12])
        more = "" if len(dropped) <= 12 else f", and {len(dropped) - 12} more"
        flags.append(Flag(
            kind="amount_dropped", severity="info", field=None,
            message=f"Numbers in the original that are not in the recipe: {shown}{more}.",
        ))
    return flags
