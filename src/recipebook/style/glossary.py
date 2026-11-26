"""The house glossary: one preferred name for each ingredient."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlossaryEntry:
    preferred: str
    variants: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_GLOSSARY: tuple[GlossaryEntry, ...] = (
    GlossaryEntry("coarse salt", ("kosher salt", "coarse kosher salt")),
    GlossaryEntry("flaky sea salt", ("flaked sea salt", "sea salt flakes")),
    GlossaryEntry("freshly ground pepper", ("freshly ground black pepper", "fresh ground black pepper", "fresh ground pepper")),
    GlossaryEntry("all-purpose flour", ("all purpose flour", "AP flour", "plain flour")),
    GlossaryEntry("self-rising flour", ("self rising flour", "self-raising flour", "self raising flour")),
    GlossaryEntry("cornstarch", ("corn starch",)),
    GlossaryEntry("baking soda", ("bicarbonate of soda", "bicarb soda")),
    GlossaryEntry("granulated sugar", ("granulated white sugar", "white granulated sugar", "white sugar")),
    GlossaryEntry("light-brown sugar", ("light brown sugar",)),
    GlossaryEntry("dark-brown sugar", ("dark brown sugar",)),
    GlossaryEntry("confectioners’ sugar", ("confectioners' sugar", "confectioner's sugar", "confectioner’s sugar", "confectioners sugar", "powdered sugar", "icing sugar")),
    GlossaryEntry("pure maple syrup", ("maple syrup",)),
    GlossaryEntry("pure vanilla extract", ("vanilla extract", "vanilla essence")),
    GlossaryEntry("unsalted butter", ("sweet butter",)),
    GlossaryEntry("heavy cream", ("heavy whipping cream", "whipping cream")),
    GlossaryEntry("half-and-half", ("half and half", "half & half")),
    GlossaryEntry("plain yogurt", ("natural yogurt", "natural yoghurt", "plain yoghurt")),
    GlossaryEntry("extra-virgin olive oil", ("extra virgin olive oil", "EVOO")),
    GlossaryEntry("semisweet chocolate", ("semi-sweet chocolate", "semi sweet chocolate")),
    GlossaryEntry("bittersweet chocolate", ("bitter-sweet chocolate", "bitter sweet chocolate")),
    GlossaryEntry("old-fashioned rolled oats", ("old fashioned rolled oats", "old-fashioned oats", "old fashioned oats", "rolled oats")),
    GlossaryEntry("golden raisins", ("sultanas",)),
    GlossaryEntry("scallions", ("green onions", "spring onions")),
    GlossaryEntry("cilantro", ("fresh coriander", "coriander leaves")),
    GlossaryEntry("zucchini", ("courgettes", "courgette")),
    GlossaryEntry("eggplant", ("aubergines", "aubergine")),
    GlossaryEntry("bell pepper", ("capsicum",)),
    GlossaryEntry("ground beef", ("minced beef", "beef mince")),
    GlossaryEntry("Parmesan", ("parmesan",)),
    GlossaryEntry("Dijon mustard", ("dijon mustard",)),
)


def apply_glossary(text: str, entries=DEFAULT_GLOSSARY) -> str:
    """Replace known variants with the preferred name.

    Text that already uses a preferred name is protected first, so a variant inside it
    ("vanilla extract" inside "pure vanilla extract") is not replaced a second time.
    """
    slots: list[str] = []

    def hold(replacement: str):
        def _hold(_match: re.Match) -> str:
            slots.append(replacement)
            return f"\x00{len(slots) - 1}\x00"

        return _hold

    def pattern(phrase: str) -> re.Pattern:
        return re.compile(r"(?<![\w\x00-])" + re.escape(phrase) + r"(?![\w\x00-])", re.IGNORECASE)

    for entry in entries:
        text = pattern(entry.preferred).sub(hold(entry.preferred), text)
    pairs = [(variant, entry.preferred) for entry in entries for variant in entry.variants]
    for variant, preferred in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
        text = pattern(variant).sub(hold(preferred), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)
