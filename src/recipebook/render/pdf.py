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
    notes_lines: int = 0  # ruled lines added under a one-page recipe with room to spare
    qr: bool = False  # QR code to the web source, placed beside the notes lines


MM = 96 / 25.4  # WeasyPrint lays out in CSS pixels
NOTES_MIN_FREE_MM = 25
QR_MIN_FREE_MM = 22
NOTES_LINE_MM = 7.2
NOTES_OVERHEAD_MM = 11  # the gap above the block plus its label
QR_BLOCK_MM = 28  # the code, its caption, and the gap above


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


def qr_data_uri(url: str) -> str:
    import segno

    return segno.make(url, error="m").svg_data_uri(border=0, dark="#2b2b2b", scale=4)


def recipe_context(recipe: Recipe, layout: Layout) -> dict:
    """What the recipe section template needs for one recipe in a chosen layout."""
    return dict(
        recipe=recipe, layout=layout.kind, body_pt=layout.body_pt, meta=_meta(recipe),
        notes_lines=layout.notes_lines,
        qr_uri=qr_data_uri(recipe.source.url) if layout.qr and recipe.source.url else None,
    )


def recipe_html(recipe: Recipe, layout: Layout, binding: Binding, page_numbers: bool) -> str:
    return _env.get_template("recipe.html.j2").render(
        binding=binding, page_numbers=page_numbers, **recipe_context(recipe, layout))


def _render(recipe: Recipe, layout: Layout, binding: Binding, page_numbers: bool):
    html = recipe_html(recipe, layout, binding, page_numbers)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES) + "/").render()


def free_space_mm(document) -> float:
    """Unused height at the bottom of a one-page recipe."""
    root = document.pages[0]._page_box
    section = next(box for box in root.descendants() if getattr(box, "element_tag", None) == "section")
    return (root.height - section.height) / MM


def _with_extras(recipe: Recipe, layout: Layout, document, binding: Binding, page_numbers: bool,
                 notes: bool, qr: bool):
    """Fill spare room on a one-page recipe with notes lines and, for web sources, a QR code."""
    free = free_space_mm(document)
    want_qr = qr and recipe.source.kind == "web" and bool(recipe.source.url) and free >= QR_MIN_FREE_MM
    lines = int((free - NOTES_OVERHEAD_MM) // NOTES_LINE_MM) if notes and free >= NOTES_MIN_FREE_MM else 0
    if want_qr and lines == 0 and free < QR_BLOCK_MM:
        want_qr = False
    while lines > 0 or want_qr:
        candidate = Layout(layout.kind, layout.body_pt, 1, notes_lines=lines, qr=want_qr)
        rendered = _render(recipe, candidate, binding, page_numbers)
        if len(rendered.pages) == 1:
            return candidate, rendered
        if lines > 0:
            lines -= 1  # measured space was a touch optimistic; give a line back
        else:
            want_qr = False
    return layout, document


def lay_out(recipe: Recipe, binding: str = "none", page_numbers: bool = False, *, notes: bool = False, qr: bool = False):
    """Choose the layout for a recipe. Returns (Layout, rendered WeasyPrint document).

    One page at 8.5 pt if it fits, stepping down to 8.0 pt. Otherwise a two-page spread
    at 9 pt, then 8.5 pt. Otherwise the spread template left to run over further pages.
    With notes or qr set, a one-page recipe with room to spare gets ruled lines and a QR code.
    """
    chosen = BINDINGS[binding]
    for size in ONE_PAGE_SIZES:
        layout = Layout("page", size, 1)
        document = _render(recipe, layout, chosen, page_numbers)
        if len(document.pages) == 1:
            if notes or qr:
                return _with_extras(recipe, layout, document, chosen, page_numbers, notes, qr)
            return layout, document
    for size in SPREAD_SIZES:
        document = _render(recipe, Layout("spread", size, 2), chosen, page_numbers)
        if len(document.pages) == 2:
            return Layout("spread", size, 2), document
    document = _render(recipe, Layout("flow", FLOW_SIZE, 0), chosen, page_numbers)
    return Layout("flow", FLOW_SIZE, len(document.pages)), document


def render_recipe_pdf(recipe: Recipe, binding: str = "none", page_numbers: bool = False) -> tuple[bytes, Layout]:
    layout, document = lay_out(recipe, binding, page_numbers)
    return document.write_pdf(), layout
