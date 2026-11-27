import sqlite3

from recipebook.intake.jobs import Job, JobStore
from recipebook.intake.material import SourceMaterial
from recipebook.intake.ocr import reading_order
from recipebook.intake.readers import _find_recipe
from recipebook.library import Library
from recipebook.model import DEFAULT_CATEGORIES


def line(text, x, top, width=0.38, height=0.02):
    return (text, 1.0, [x, top - height, width, height])


def test_two_column_page_reads_left_column_then_right():
    found = [
        line("Pecan Pie", 0.1, 0.95, width=0.5),
        line("A soft filling that sets up well, for any holiday table.", 0.1, 0.90, width=0.8),
        line("1 cup corn syrup", 0.1, 0.80), line("Preheat oven to 350 degrees.", 0.55, 0.80),
        line("3 eggs", 0.1, 0.76), line("Whisk eggs and syrup.", 0.55, 0.76),
        line("2 cups pecans", 0.1, 0.72), line("Bake 50 to 60 minutes.", 0.55, 0.72),
    ]
    assert [t for t, _c, _b in reading_order(found)] == [
        "Pecan Pie", "A soft filling that sets up well, for any holiday table.",
        "1 cup corn syrup", "3 eggs", "2 cups pecans",
        "Preheat oven to 350 degrees.", "Whisk eggs and syrup.", "Bake 50 to 60 minutes."]


def test_single_column_page_reads_top_to_bottom():
    found = [line("Step two", 0.1, 0.5, width=0.7), line("Title", 0.1, 0.9, width=0.3), line("Step one", 0.1, 0.7, width=0.75)]
    assert [t for t, _c, _b in reading_order(found)] == ["Title", "Step one", "Step two"]


def test_recipe_data_found_under_main_entity():
    page = {"@type": "WebPage", "mainEntity": {"@type": "Recipe", "recipeIngredient": ["x"]}}
    assert _find_recipe(page)["@type"] == "Recipe"
    assert _find_recipe([{"@type": "WebSite"}, {"@graph": [{"@type": "Recipe", "name": "y"}]}])["name"] == "y"
    assert _find_recipe({"@type": "Article", "author": {"@type": "Person"}}) is None


def test_renaming_a_category_updates_the_remembered_book_choices(tmp_path):
    library = Library(tmp_path / "library.db")
    library.set_setting("book_options", {"title": "T", "categories": ["Main Dishes", "Desserts & Baking"]})
    library.set_categories(DEFAULT_CATEGORIES[:4] + ["Sweets & Breads"])
    assert library.get_setting("book_options")["categories"] == ["Main Dishes", "Sweets & Breads"]
    library.set_setting("book_options", {"title": "T", "categories": None})
    library.set_categories(DEFAULT_CATEGORIES)
    assert library.get_setting("book_options")["categories"] is None
