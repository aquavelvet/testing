"""Read one ingredient line into its parts, and write it back in house style."""

from __future__ import annotations

import re

from ..model import Ingredient
from .glossary import DEFAULT_GLOSSARY, apply_glossary
from .numbers import format_range, normalize_fractions, parse_quantity_prefix
from .units import match_unit_prefix, unit_word

_BULLET = re.compile(r"^\s*(?:[-*•·▢☐□]+|\d+[.)](?=\s+\d))\s*")
_PAREN = re.compile(r"\s*\([^()]*\)")
_LEADING_PAREN = re.compile(r"^\(([^()]*)\)\s*")

# Words that open the preparation part of a line: "..., peeled and chopped".
_PREP_STARTERS = (
    "at room temperature|room temperature|plus|such as|for |to |or |about|optional|preferably|if |"
    "cut|cold|warm|cooled|chilled|well|very|finely|coarsely|roughly|thinly|thickly|lightly|freshly|"
    "halved|quartered|divided|separated|in |on |with |without|skin|bone|stems?|leaves|white|ends?|"
    "juice|zest|thawed|fresh or"
)
_PREP_START_RE = re.compile(rf"^(?:{_PREP_STARTERS})", re.IGNORECASE)
_OPTIONAL_RE = re.compile(
    r"\(optional\)|,\s*optional\b|^optional\b|\bfor (?:serving|garnish|garnishing)\b|\bto serve\b",
    re.IGNORECASE,
)


def _looks_like_prep(segment: str) -> bool:
    segment = segment.strip()
    if _PREP_START_RE.match(segment):
        return True
    first = segment.split(" ", 1)[0].rstrip(",.;").lower()
    return first.endswith(("ed", "ly")) and len(first) > 3


def _split_item_prep(rest: str) -> tuple[str, str | None]:
    """Split 'firm, tart apples (about 6), such as Granny Smith, peeled' at the right comma."""
    depth = 0
    for index, char in enumerate(rest):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0 and _looks_like_prep(rest[index + 1:]):
            return rest[:index].strip(), rest[index + 1:].strip() or None
    return rest.strip(), None


def _canonical_item(item: str) -> str:
    item = _PAREN.sub("", item)
    item = re.sub(r"\s+", " ", item).strip(" ,.;").lower()
    return re.sub(r"^of\s+", "", item)


def _tidy(text: str) -> str:
    text = text.replace(" ", " ")
    text = re.sub(r"(?<=\w)'(?=\w)|(?<=s)'(?=\s|$)", "’", text)  # typographic apostrophe
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,;.])", r"\1", text)


def parse_ingredient_line(line: str, glossary=DEFAULT_GLOSSARY) -> Ingredient:
    """Normalize a line to house style and derive quantity, unit, item, prep, and optional."""
    raw = _tidy(_BULLET.sub("", line))
    if not raw:
        return Ingredient(text="")

    quantity, quantity_max, rest = parse_quantity_prefix(raw)

    # "1 (15-ounce) can pumpkin": a size note may sit between the amount and the unit.
    size_note = ""
    if quantity is not None:
        note = _LEADING_PAREN.match(rest)
        if note:
            size_note = f"({normalize_fractions(note.group(1))})"
            rest = rest[note.end():]

    unit, after_unit = match_unit_prefix(rest)
    if unit is not None and not after_unit.strip(" ,.;"):
        unit, after_unit = None, rest  # "2 cloves": the word is the ingredient, not a unit
    rest = after_unit

    if unit is not None and re.match(r"of\s", rest, re.IGNORECASE):
        if quantity is not None or not unit.keeps_of:
            rest = rest[3:].lstrip()

    rest = apply_glossary(normalize_fractions(rest), glossary)
    item_text, prep = _split_item_prep(rest)

    parts = []
    if quantity is not None:
        parts.append(format_range(quantity, quantity_max))
    if size_note:
        parts.append(size_note)
    if unit is not None:
        parts.append(unit_word(unit, quantity, quantity_max))
    parts.append(rest)
    text = _tidy(" ".join(part for part in parts if part))
    if text and text[0].isalpha():
        text = text[0].upper() + text[1:]

    item = _canonical_item(item_text) or None
    return Ingredient(
        text=text,
        quantity=quantity,
        quantity_max=quantity_max,
        unit=unit.name if unit else None,
        item=item,
        prep=prep,
        optional=_is_optional(rest),
    )


def _is_optional(rest: str) -> bool:
    """'Vanilla ice cream, for serving' is optional; 'sugar, plus more for serving' is not."""
    without = re.sub(r",?\s*plus (?:more|extra)[^,;]*", "", rest, flags=re.IGNORECASE)
    return bool(_OPTIONAL_RE.search(without))
