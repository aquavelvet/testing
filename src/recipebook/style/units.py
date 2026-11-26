"""Canonical units, their plurals and abbreviations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Unit:
    name: str  # canonical singular
    plural: str
    aliases: tuple[str, ...] = ()
    kind: str = "count"  # volume, weight, count, or dash
    keeps_of: bool = False  # "Pinch of salt" keeps its "of"


UNITS: tuple[Unit, ...] = (
    Unit("teaspoon", "teaspoons", ("tsp", "tsps", "teaspoonful", "teaspoonfuls"), "volume"),
    Unit("tablespoon", "tablespoons", ("tbsp", "tbsps", "tbs", "tbl", "tb", "tablespoonful", "tablespoonfuls"), "volume"),
    Unit("fluid ounce", "fluid ounces", ("fl oz", "fl. oz", "fluid oz"), "volume"),
    Unit("cup", "cups", ("c",), "volume"),
    Unit("pint", "pints", ("pt", "pts"), "volume"),
    Unit("quart", "quarts", ("qt", "qts"), "volume"),
    Unit("gallon", "gallons", ("gal", "gals"), "volume"),
    Unit("milliliter", "milliliters", ("ml", "mls", "millilitre", "millilitres", "cc"), "volume"),
    Unit("liter", "liters", ("l", "ltr", "litre", "litres"), "volume"),
    Unit("ounce", "ounces", ("oz", "ozs"), "weight"),
    Unit("pound", "pounds", ("lb", "lbs"), "weight"),
    Unit("gram", "grams", ("g", "gm", "gms", "gr"), "weight"),
    Unit("kilogram", "kilograms", ("kg", "kgs", "kilo", "kilos"), "weight"),
    Unit("milligram", "milligrams", ("mg",), "weight"),
    Unit("pinch", "pinches", (), "dash", keeps_of=True),
    Unit("dash", "dashes", (), "dash", keeps_of=True),
    Unit("drop", "drops", (), "dash", keeps_of=True),
    Unit("handful", "handfuls", (), "dash", keeps_of=True),
    Unit("can", "cans"),
    Unit("jar", "jars"),
    Unit("package", "packages", ("pkg", "pkgs", "packet", "packets")),
    Unit("stick", "sticks"),
    Unit("bunch", "bunches"),
    Unit("head", "heads"),
    Unit("sprig", "sprigs"),
    Unit("clove", "cloves"),
    Unit("slice", "slices"),
    Unit("piece", "pieces"),
    Unit("bag", "bags"),
    Unit("box", "boxes"),
    Unit("bottle", "bottles"),
    Unit("stalk", "stalks"),
    Unit("ear", "ears"),
    Unit("sheet", "sheets"),
    Unit("envelope", "envelopes"),
)

_BY_NAME: dict[str, Unit] = {}
for _unit in UNITS:
    for _word in (_unit.name, _unit.plural, *_unit.aliases):
        _BY_NAME[_word] = _unit

# Single letters are case-sensitive: T is tablespoon, t is teaspoon.
_CASE_SENSITIVE = {"T": _BY_NAME["tablespoon"], "t": _BY_NAME["teaspoon"], "L": _BY_NAME["liter"]}

# Longest first, so "fl oz" wins over "fl" and "tablespoons" over "tablespoon".
_WORDS = sorted(_BY_NAME, key=len, reverse=True)
_UNIT_RE = re.compile(
    r"(?P<word>" + "|".join(re.escape(w) for w in _WORDS) + r"|[Tt])\.?(?![\w-])",
    re.IGNORECASE,
)


def lookup(word: str) -> Unit | None:
    word = word.strip().rstrip(".")
    if word in _CASE_SENSITIVE:
        return _CASE_SENSITIVE[word]
    return _BY_NAME.get(re.sub(r"\s+", " ", word.lower()))


def match_unit_prefix(text: str) -> tuple[Unit | None, str]:
    """Read a leading unit word. Returns (unit, rest of text)."""
    stripped = text.lstrip()
    match = _UNIT_RE.match(stripped)
    if not match:
        return None, text
    unit = lookup(match.group("word"))
    if unit is None:
        return None, text
    return unit, stripped[match.end():].lstrip()


def unit_word(unit: Unit, quantity: Fraction | None, quantity_max: Fraction | None = None) -> str:
    """The spelled-out unit, plural when the amount is more than one."""
    amount = quantity_max if quantity_max is not None else quantity
    if amount is not None and amount > 1:
        return unit.plural
    return unit.name
