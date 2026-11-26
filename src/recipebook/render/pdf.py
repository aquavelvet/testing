"""Recipe to A5 PDF, including the choice of layout (auto-fit)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jinja2
import weasyprint

from ..model import Recipe, format_minutes

TEMPLATES = Path(__file__).parent / "templates"
FONTS = Path(__file__).parent / "fonts"

# Body sizes tried in order. 8.0 pt is the floor for a one-page recipe.
ONE_PAGE_SIZES = (8.5, 8.3, 8.1, 8.0)
SPREAD_SIZES = (9.0, 8.5)
FLOW_SIZE = 8.5


@dataclass(frozen=True)
class Binding:
    name: str
    inner_mm: float
    outer_mm: float


# Every binding leaves the same 120 mm text width, so a layout fits all of them alike.
BINDINGS = {
    "none": Binding("none", 14, 14),
    "bound": Binding("bound", 17, 11),
    "ring": Binding("ring", 19, 9),
}


@dataclass(frozen=True)
class Layout:
    kind: Literal["page", "spread", "flow"]
    body_pt: float
    pages: int


_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _meta(recipe: Recipe) -> list[tuple[str, str]]:
    cells = []
    if recipe.yield_value:
        cells.append((recipe.yield_label, recipe.yield_value))
    if recipe.active_minutes is not None:
        cells.append(("Active Time", format_minutes(recipe.active_minutes)))
    if recipe.total_minutes is not None:
        cells.append(("Total Time", format_minutes(recipe.total_minutes)))
    return cells


def recipe_html(recipe: Recipe, layout: str, body_pt: float, binding: Binding, page_numbers: bool) -> str:
    return _env.get_template("recipe.html.j2").render(
        recipe=recipe, layout=layout, body_pt=body_pt, binding=binding,
        page_numbers=page_numbers, meta=_meta(recipe),
    )


def _render(recipe: Recipe, layout: str, body_pt: float, binding: Binding, page_numbers: bool):
    html = recipe_html(recipe, layout, body_pt, binding, page_numbers)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES) + "/").render()


def lay_out(recipe: Recipe, binding: str = "none", page_numbers: bool = False):
    """Choose the layout for a recipe. Returns (Layout, rendered WeasyPrint document).

    One page at 8.5 pt if it fits, stepping down to 8.0 pt. Otherwise a two-page spread
    at 9 pt, then 8.5 pt. Otherwise the spread template left to run over further pages.
    """
    chosen = BINDINGS[binding]
    for size in ONE_PAGE_SIZES:
        document = _render(recipe, "page", size, chosen, page_numbers)
        if len(document.pages) == 1:
            return Layout("page", size, 1), document
    for size in SPREAD_SIZES:
        document = _render(recipe, "spread", size, chosen, page_numbers)
        if len(document.pages) == 2:
            return Layout("spread", size, 2), document
    document = _render(recipe, "flow", FLOW_SIZE, chosen, page_numbers)
    return Layout("flow", FLOW_SIZE, len(document.pages)), document


def render_recipe_pdf(recipe: Recipe, binding: str = "none", page_numbers: bool = False) -> tuple[bytes, Layout]:
    layout, document = lay_out(recipe, binding, page_numbers)
    return document.write_pdf(), layout
