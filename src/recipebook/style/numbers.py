"""Reading and writing recipe quantities as exact fractions."""

from __future__ import annotations

import re
from fractions import Fraction

UNICODE_FRACTIONS = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
}
GLYPH_FOR = {value: glyph for glyph, value in UNICODE_FRACTIONS.items()}
_GLYPHS = "".join(UNICODE_FRACTIONS)

# One quantity. Order matters: the longest forms are tried first.
_QTY = (
    rf"(?:(?P<mw>\d+)\s?(?P<mg>[{_GLYPHS}])"  # 1½ or 1 ½
    rf"|(?P<g>[{_GLYPHS}])"  # ½
    r"|(?P<aw>\d+)[ -](?P<an>\d+)\s?[/⁄]\s?(?P<ad>\d+)"  # 1 1/2 or 1-1/2
    r"|(?P<n>\d+)\s?[/⁄]\s?(?P<d>\d+)"  # 1/2
    r"|(?P<dec>\d+\.\d+|\.\d+)"  # 0.5 or .5
    r"|(?P<i>\d+))"  # 2
)
QUANTITY_RE = re.compile(_QTY)
_RANGE_SEP = re.compile(r"\s*(?:to|-|–|—)\s*", re.IGNORECASE)


def _snap(value: Fraction) -> Fraction:
    """Turn a rounded decimal such as 0.33 into the kitchen fraction it stands for."""
    if value.denominator in (1, 2, 3, 4, 8):
        return value
    nearest = value.limit_denominator(8)
    if nearest.denominator in (2, 3, 4, 8) and abs(nearest - value) <= Fraction(1, 50):
        return nearest
    return value


def _value(match: re.Match) -> Fraction | None:
    g = match.groupdict()
    try:
        if g["mw"] is not None:
            return int(g["mw"]) + UNICODE_FRACTIONS[g["mg"]]
        if g["g"] is not None:
            return UNICODE_FRACTIONS[g["g"]]
        if g["aw"] is not None:
            return int(g["aw"]) + Fraction(int(g["an"]), int(g["ad"]))
        if g["n"] is not None:
            return Fraction(int(g["n"]), int(g["d"]))
        if g["dec"] is not None:
            return _snap(Fraction(g["dec"]))
        return Fraction(int(g["i"]))
    except ZeroDivisionError:
        return None


def parse_quantity_prefix(text: str) -> tuple[Fraction | None, Fraction | None, str]:
    """Read a leading quantity or range. Returns (quantity, quantity_max, rest of text)."""
    text = text.lstrip()
    first = QUANTITY_RE.match(text)
    if not first:
        return None, None, text
    quantity = _value(first)
    if quantity is None:
        return None, None, text
    rest = text[first.end():]
    sep = _RANGE_SEP.match(rest)
    if sep:
        second = QUANTITY_RE.match(rest, sep.end())
        if second:
            upper = _value(second)
            if upper is not None and upper > quantity:
                return quantity, upper, rest[second.end():].lstrip()
    return quantity, None, rest.lstrip()


def format_quantity(value: Fraction) -> str:
    """Fraction(3, 2) -> '1½'. Uses fraction characters where one exists."""
    value = Fraction(value)
    whole, part = divmod(value, 1)
    if part == 0:
        return str(whole)
    glyph = GLYPH_FOR.get(part)
    if glyph:
        return f"{whole}{glyph}" if whole else glyph
    if 10 ** 6 % value.denominator == 0:  # a clean decimal such as 0.7 or 2.25
        return f"{float(value):g}"
    return f"{whole} {part.numerator}/{part.denominator}" if whole else f"{part.numerator}/{part.denominator}"


def format_range(quantity: Fraction | None, quantity_max: Fraction | None) -> str:
    if quantity is None:
        return ""
    if quantity_max is None:
        return format_quantity(quantity)
    return f"{format_quantity(quantity)} to {format_quantity(quantity_max)}"


_ASCII_FRACTION = re.compile(r"(?<![\d/⁄.])(?:(\d+)[ -])?(\d+)\s?[/⁄]\s?(\d+)(?![\d/⁄])")


def normalize_fractions(text: str) -> str:
    """Replace typed fractions in running text with fraction characters: 1/2-inch -> ½-inch.

    Fractions with no single character (9/13, dates) are left alone.
    """

    def swap(match: re.Match) -> str:
        whole, num, den = match.group(1), int(match.group(2)), int(match.group(3))
        if den == 0:
            return match.group(0)
        part = Fraction(num, den)
        if part >= 1 or part not in GLYPH_FOR:
            return match.group(0)
        return f"{whole or ''}{GLYPH_FOR[part]}"

    return _ASCII_FRACTION.sub(swap, text)


def find_numbers(text: str) -> list[Fraction]:
    """Every quantity in a text, in order. Used by the fidelity check."""
    found = []
    for match in QUANTITY_RE.finditer(text):
        value = _value(match)
        if value is not None:
            found.append(value)
    return found
