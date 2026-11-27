import pypdfium2 as pdfium
import pytest

import samples
from recipebook.library import Library
from recipebook.render.book import BookOptions, arrange, build_book, select_recipes
from recipebook.render.pdf import Layout

from test_render import squash


def variant(base, title, category, **changes):
    return base.model_copy(update={"id": None, "title": title, "category": category, **changes})


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    library = Library(tmp_path_factory.mktemp("book") / "library.db")
    short, medium, long = samples.short(), samples.medium(), samples.long()
    for recipe in [
        variant(long, "Pumpkin Layer Cake", "Desserts & Baking"),
        variant(medium, "Apple-Cranberry Crisp", "Desserts & Baking", tags=["Thanksgiving", "Fall"]),
        variant(short, "Maple Whipped Cream", "Desserts & Baking", tags=["thanksgiving"]),
        variant(long, "Zucchini Lasagna", "Main Dishes"),
        variant(long, "Braised Short Ribs", "Main Dishes"),
        variant(short, "Buttermilk Pancakes", "Breakfast & Brunch"),
        variant(medium, "Cornbread Stuffing", "Salads & Sides", tags=["Thanksgiving"]),
    ]:
        library.save(recipe)
    return library


@pytest.fixture(scope="module")
def book(library):
    return build_book(library, BookOptions(title="Test Kitchen", subtitle="Collected", edition="2026 Edition"))


def pages_text(result):
    pdf = pdfium.PdfDocument(result.pdf)
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


def test_sections_follow_category_order_and_skip_empty_ones(library):
    sections = select_recipes(library, BookOptions())
    assert [s.name for s in sections] == ["Breakfast & Brunch", "Main Dishes", "Salads & Sides", "Desserts & Baking"]
    assert [s.ordinal for s in sections] == ["One", "Two", "Three", "Four"]
    assert [r.title for r in sections[3].recipes] == ["Apple-Cranberry Crisp", "Maple Whipped Cream", "Pumpkin Layer Cake"]


def test_book_has_every_part_in_order(book):
    text = [squash(page) for page in pages_text(book)]
    assert book.recipe_count == 7 and book.pages == len(text)
    assert "testkitchen" in text[0] and "2026edition" in text[0]
    assert text[1].startswith("contents") and "index" in text[1]
    assert text[-1].startswith("index")
    assert squash("Part One") in text[2] and squash("Breakfast & Brunch") in text[2]


def test_spreads_start_left_and_dividers_fall_right(book, library):
    assert book.report == [line for line in book.report if "notes page" in line]  # no placement problems
    for recipe_id, first in book.recipe_pages.items():
        if "Lasagna" in library.get(recipe_id).title or "Ribs" in library.get(recipe_id).title or "Cake" in library.get(recipe_id).title:
            assert first % 2 == 0, f"spread No. {recipe_id} starts on page {first}"
    text = pages_text(book)
    for number, page in enumerate(text, start=1):
        if squash("Part ") in squash(page)[:12]:
            assert number % 2 == 1, f"divider on page {number}"


def test_contents_and_index_numbers_match_real_pages(book, library):
    text = pages_text(book)
    contents, index = text[1], text[-1]
    for recipe_id, first in book.recipe_pages.items():
        title = library.get(recipe_id).title
        assert squash(title) in squash(text[first - 1]), f"{title} is not on page {first}"
        line = next(line for line in contents.splitlines() if line.startswith(title))
        assert line.rstrip().endswith(str(first)), line
        assert f"{title}, {first}" in index.replace("\r", "")


def test_page_map_covers_both_pages_of_a_spread(book, library):
    cake = next(i for i in book.recipe_pages if library.get(i).title == "Pumpkin Layer Cake")
    first = book.recipe_pages[cake]
    assert book.page_map[first] == cake and book.page_map[first + 1] == cake
    assert 1 not in book.page_map and 2 not in book.page_map


def test_page_numbers_print_on_recipe_pages(book):
    text = pages_text(book)
    first = min(book.recipe_pages.values())
    assert str(first) in text[first - 1].split()


def test_tag_and_category_filters(library):
    thanksgiving = build_book(library, BookOptions(tag="Thanksgiving"))
    assert thanksgiving.recipe_count == 3
    desserts = build_book(library, BookOptions(categories=["Desserts & Baking"]))
    assert desserts.recipe_count == 3
    with pytest.raises(ValueError, match="nothing to put in the book"):
        build_book(library, BookOptions(tag="No such tag"))


def test_layouts_are_cached_until_the_recipe_changes(library, book):
    summary = library.list("Breakfast & Brunch")[0]
    recipe = library.get(summary.id)
    key = f"{recipe.updated_at.isoformat()}|1|1"
    assert library.get_layout(recipe.id, key)["kind"] == "page"
    library.save(recipe)  # saving changes updated_at
    assert library.get_layout(recipe.id, f"{library.get(recipe.id).updated_at.isoformat()}|1|1") is None


def test_arrange_moves_a_single_page_recipe_ahead_of_a_spread(library):
    section = select_recipes(library, BookOptions(categories=["Desserts & Baking"]))[0]
    crisp, cream, cake = section.recipes
    layouts = {crisp.id: Layout("spread", 9.0, 2), cream.id: Layout("page", 8.5, 1), cake.id: Layout("spread", 9.0, 2)}
    items = arrange([section], layouts, first_page=3)
    order = [(i.kind, i.recipe.title if i.recipe else None, i.page) for i in items]
    # divider on 3; the crisp spread would start on 4 (left) so it goes first; then page 6 is left again
    assert order == [("divider", None, 3), ("recipe", "Apple-Cranberry Crisp", 4), ("recipe", "Pumpkin Layer Cake", 6),
                     ("recipe", "Maple Whipped Cream", 8)]
    items = arrange([section], layouts, first_page=4)  # page 4 is a left page: filler, then the divider on 5
    order = [(i.kind, i.recipe.title if i.recipe else None, i.page) for i in items]
    assert order[:2] == [("notes", None, 4), ("divider", None, 5)]
    assert order[2:] == [("recipe", "Apple-Cranberry Crisp", 6), ("recipe", "Pumpkin Layer Cake", 8), ("recipe", "Maple Whipped Cream", 10)]
    only_spreads = {crisp.id: Layout("spread", 9.0, 2), cream.id: Layout("spread", 9.0, 2), cake.id: Layout("page", 8.5, 1)}
    items = arrange([section], only_spreads, first_page=2)
    order = [(i.kind, i.recipe.title if i.recipe else None, i.page) for i in items]
    # filler on 2, divider on 3, crisp on 4-5, cream on 6-7, cake on 8
    assert [o[2] for o in order] == [2, 3, 4, 6, 8]


def test_editions_are_recorded(library):
    first = library.add_edition("Test Kitchen", "test-kitchen-2026-11-27.pdf", {"pages": 12, "page_map": {"4": 7}})
    second = library.add_edition("Test Kitchen", "test-kitchen-2026-11-28.pdf", {"pages": 14, "page_map": {}})
    editions = library.editions()
    assert [e["id"] for e in editions] == [second, first] and editions[1]["page_map"] == {"4": 7}
    assert library.get_edition(first)["pages"] == 12 and library.get_edition(999) is None
