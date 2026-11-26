import pytest

from recipebook.library import Library
from recipebook.model import DEFAULT_CATEGORIES, Ingredient, IngredientGroup, Recipe, Step
from recipebook.style.glossary import DEFAULT_GLOSSARY, GlossaryEntry


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "library.db")


def make(title="Shortbread", category="Desserts & Baking"):
    return Recipe(
        title=title, category=category,
        ingredient_groups=[IngredientGroup(items=[Ingredient(text="1 cup butter")])],
        steps=[Step(text="Bake.")],
    )


def test_save_assigns_a_number_and_round_trips(library):
    saved = library.save(make())
    assert saved.id == 1
    loaded = library.get(1)
    assert loaded.title == "Shortbread" and loaded.id == 1
    assert loaded.ingredients()[0].text == "1 cup butter"


def test_update_keeps_the_number(library):
    saved = library.save(make())
    library.save(saved.model_copy(update={"title": "Brown-Butter Shortbread"}))
    assert library.get(saved.id).title == "Brown-Butter Shortbread"
    assert len(library.list()) == 1


def test_numbers_are_never_reused(library):
    first = library.save(make("A"))
    second = library.save(make("B"))
    library.delete(second.id)
    library.delete(first.id)
    third = library.save(make("C"))
    assert third.id == 3


def test_list_is_alphabetical_and_filters_by_category(library):
    library.save(make("pecan pie"))
    library.save(make("Apple Crisp"))
    library.save(make("Roast Chicken", "Main Dishes"))
    assert [s.title for s in library.list()] == ["Apple Crisp", "pecan pie", "Roast Chicken"]
    assert [s.title for s in library.list("Main Dishes")] == ["Roast Chicken"]


def test_get_and_delete_missing(library):
    assert library.get(99) is None
    assert library.delete(99) is False
    with pytest.raises(KeyError):
        library.save(make().model_copy(update={"id": 99}))


def test_categories_default_and_rename_moves_recipes(library):
    assert library.categories() == DEFAULT_CATEGORIES
    saved = library.save(make())
    renamed = DEFAULT_CATEGORIES[:4] + ["Sweets & Breads"]
    library.set_categories(renamed)
    assert library.categories() == renamed
    assert library.get(saved.id).category == "Sweets & Breads"
    assert [s.title for s in library.list("Sweets & Breads")] == ["Shortbread"]


@pytest.mark.parametrize("bad", [
    DEFAULT_CATEGORIES[:4],
    DEFAULT_CATEGORIES[:4] + [" "],
    DEFAULT_CATEGORIES[:4] + [DEFAULT_CATEGORIES[0]],
])
def test_categories_must_be_five_distinct_names(library, bad):
    with pytest.raises(ValueError):
        library.set_categories(bad)


def test_glossary_is_seeded_and_editable(library):
    assert library.glossary() == DEFAULT_GLOSSARY
    library.set_glossary([GlossaryEntry("coarse salt", ("kosher salt",))])
    assert library.glossary() == (GlossaryEntry("coarse salt", ("kosher salt",)),)


def test_library_reopens_with_its_data(tmp_path):
    Library(tmp_path / "library.db").save(make())
    again = Library(tmp_path / "library.db")
    assert again.get(1).title == "Shortbread"
    assert len(again.glossary()) == len(DEFAULT_GLOSSARY)
