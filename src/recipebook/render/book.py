"""Assemble the whole recipe book: cover, contents, sections, recipes, index."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby

import weasyprint

from ..library import Library
from ..model import Recipe
from .pdf import BINDINGS, TEMPLATES, Layout, _env, lay_out, recipe_context

ORDINALS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]


@dataclass
class BookOptions:
    title: str = "Recipes from Our Kitchen"
    subtitle: str = ""
    kicker: str = "A Family Cookbook"
    edition: str = ""
    categories: list[str] | None = None  # None means every category
    tag: str | None = None  # only recipes carrying this tag
    binding: str = "bound"
    notes: bool = True
    qr: bool = True


@dataclass
class Section:
    name: str
    ordinal: str
    anchor: str
    recipes: list[Recipe]


@dataclass
class Item:
    kind: str  # divider, recipe, notes
    section: Section | None = None
    recipe: Recipe | None = None
    layout: Layout | None = None
    context: dict = field(default_factory=dict)
    page: int = 0  # the page this item is planned to start on


@dataclass
class BookResult:
    pdf: bytes
    pages: int
    recipe_pages: dict[int, int]  # recipe number -> its first page
    page_map: dict[int, int]  # page -> recipe number, for every recipe page
    report: list[str]
    recipe_count: int


def select_recipes(library: Library, options: BookOptions) -> list[Section]:
    wanted = options.categories if options.categories is not None else library.categories()
    tag = (options.tag or "").strip().lower()
    sections = []
    for name in library.categories():
        if name not in wanted:
            continue
        recipes = [library.get(summary.id) for summary in library.list(name)]
        if tag:
            recipes = [r for r in recipes if tag in {t.lower() for t in r.tags}]
        if recipes:
            ordinal = ORDINALS[len(sections)] if len(sections) < len(ORDINALS) else str(len(sections) + 1)
            sections.append(Section(name, ordinal, f"s{len(sections) + 1}", recipes))
    return sections


def cached_layout(library: Library, recipe: Recipe, options: BookOptions) -> Layout:
    """The layout for a recipe, reused until the recipe or the notes and QR switches change."""
    key = f"{recipe.updated_at.isoformat()}|{int(options.notes)}|{int(options.qr)}"
    stored = library.get_layout(recipe.id, key)
    if stored:
        return Layout(**stored)
    layout, _ = lay_out(recipe, options.binding, True, notes=options.notes, qr=options.qr)
    library.set_layout(recipe.id, key, layout.__dict__)
    return layout


def arrange(sections: list[Section], layouts: dict[int, Layout], first_page: int) -> list[Item]:
    """Put dividers and recipes in page order.

    Dividers fall on right-hand (odd) pages. Spreads and longer recipes start on left-hand
    (even) pages. Recipes are alphabetical within a section, except where swapping a
    one-page recipe and a spread avoids a gap; when no swap helps, a ruled notes page fills it.
    """
    items: list[Item] = []
    page = first_page

    def place(item: Item, length: int) -> None:
        nonlocal page
        item.page = page
        items.append(item)
        page += length

    for section in sections:
        if page % 2 == 0:
            place(Item("notes"), 1)
        place(Item("divider", section=section), 1)
        queue = list(section.recipes)
        while queue:
            recipe = queue[0]
            singles = [r for r in queue if layouts[r.id].kind == "page"]
            if page % 2 == 0 and layouts[recipe.id].kind == "page" and len(singles) % 2 == 1 and len(singles) < len(queue):
                # On a left-hand page with an odd number of one-page recipes left, placing one now
                # would strand a later spread on a right-hand page. Take the next spread first.
                recipe = next(r for r in queue if layouts[r.id].kind != "page")
            elif layouts[recipe.id].kind != "page" and page % 2 == 1:
                single = singles[0] if singles else None
                if single is None:
                    place(Item("notes"), 1)
                    continue
                recipe = single
            queue.remove(recipe)
            layout = layouts[recipe.id]
            place(Item("recipe", recipe=recipe, layout=layout, context=recipe_context(recipe, layout)), layout.pages)
    return items


def _anchors(document) -> dict[str, int]:
    found = {}
    for number, page in enumerate(document.pages, start=1):
        for name in page.anchors:
            found.setdefault(name, number)
    return found


def build_book(library: Library, options: BookOptions) -> BookResult:
    sections = select_recipes(library, options)
    if not sections:
        raise ValueError("No saved recipes match these choices, so there is nothing to put in the book.")
    binding = BINDINGS[options.binding]
    recipes = [recipe for section in sections for recipe in section.recipes]
    layouts = {recipe.id: cached_layout(library, recipe, options) for recipe in recipes}
    titles = sorted(recipes, key=lambda r: r.title.lower())
    index = [(letter, list(group)) for letter, group in groupby(titles, key=lambda r: r.title[:1].upper())]
    template = _env.get_template("book.html.j2")

    contents_pages = 1
    for _attempt in range(4):  # the contents length is only known after a render
        items = arrange(sections, layouts, first_page=2 + contents_pages)
        html = template.render(book=options, binding=binding, sections=sections, items=items, index=index)
        document = weasyprint.HTML(string=html, base_url=str(TEMPLATES) + "/").render()
        anchors = _anchors(document)
        drift = anchors[items[0].section.anchor if items[0].kind == "divider" else items[1].section.anchor] - (
            items[0].page if items[0].kind == "divider" else items[1].page)
        if drift == 0:
            break
        contents_pages += drift

    report: list[str] = []
    recipe_pages: dict[int, int] = {}
    page_map: dict[int, int] = {}
    for item in items:
        if item.kind == "divider" and anchors[item.section.anchor] % 2 == 0:
            report.append(f"The “{item.section.name}” divider landed on a left-hand page.")
        if item.kind != "recipe":
            continue
        first = anchors[f"r{item.recipe.id}"]
        recipe_pages[item.recipe.id] = first
        for offset in range(item.layout.pages):
            page_map[first + offset] = item.recipe.id
        if item.layout.kind != "page" and first % 2 == 1:
            report.append(f"No. {item.recipe.id} “{item.recipe.title}” is a spread but starts on a right-hand page.")
        if item.layout.kind == "flow":
            report.append(f"No. {item.recipe.id} “{item.recipe.title}” is too long for two pages and runs to "
                          f"{item.layout.pages}.")
    fillers = sum(1 for item in items if item.kind == "notes")
    if fillers:
        report.append(f"{fillers} ruled notes page{'' if fillers == 1 else 's'} added to keep spreads and "
                      "section openers on the correct side.")
    return BookResult(pdf=document.write_pdf(), pages=len(document.pages), recipe_pages=recipe_pages,
                      page_map=page_map, report=report, recipe_count=len(recipes))
