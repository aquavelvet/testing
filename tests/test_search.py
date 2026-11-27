import sqlite3

import pytest

import samples
from recipebook.library import Library
from recipebook.model import Source


@pytest.fixture
def library(tmp_path):
    library = Library(tmp_path / "library.db")
    for recipe in (samples.short(), samples.medium(), samples.long()):
        library.save(recipe.model_copy(update={"id": None}))
    return library  # 1 Maple Whipped Cream, 2 Apple-Cranberry Crisp, 3 Pumpkin Layer Cake


def titles(results):
    return [r.title.split(" with ")[0] for r in results]


def test_search_by_title_ingredient_tag_and_source(library):
    assert titles(library.search("crisp")) == ["Apple-Cranberry Crisp"]
    assert titles(library.search("cranberries")) == ["Apple-Cranberry Crisp"]
    assert titles(library.search("purée")) == titles(library.search("puree")) == ["Pumpkin Layer Cake"]
    assert titles(library.search("Sample Cookbook")) == ["Pumpkin Layer Cake"]
    assert titles(library.search("example.com")) == ["Maple Whipped Cream"]
    assert len(library.search("desserts")) == 3  # category is searchable
    assert library.search("anchovies") == []


def test_title_matches_rank_above_ingredient_matches(library):
    assert titles(library.search("maple"))[0] == "Maple Whipped Cream"
    assert set(titles(library.search("maple"))) == {"Maple Whipped Cream", "Pumpkin Layer Cake"}


def test_all_words_must_match_and_last_word_may_be_partial(library):
    assert titles(library.search("pump")) == ["Pumpkin Layer Cake"]
    assert titles(library.search("cream cheese")) == ["Pumpkin Layer Cake"]
    assert library.search("cream anchovy") == []


def test_number_lookup(library):
    for query in ("2", "#2", "No. 2", "no 2"):
        assert library.search(query)[0].id == 2, query
    assert library.search("#99") == []
    assert [r.id for r in library.search("#2")] == [2]  # an explicit number asks for that recipe only
    assert library.search("9")[0].title.startswith("Apple")  # no recipe 9, but "9-by-13-inch" matches


def test_odd_input_is_safe(library):
    for query in ('"', "a AND OR", "*", "(crisp", "crisp)", "it's", "  ", "ñ-ü"):
        library.search(query)
    assert len(library.search("   ")) == 3


def test_index_follows_edits_and_deletes(library):
    recipe = library.get(1)
    library.save(recipe.model_copy(update={"title": "Bourbon Whipped Cream", "tags": ["Christmas"]}))
    assert titles(library.search("bourbon")) == ["Bourbon Whipped Cream"]
    assert titles(library.search("christmas")) == ["Bourbon Whipped Cream"]
    assert "Maple Whipped Cream" not in titles(library.search("maple whipped"))
    library.delete(1)
    assert library.search("bourbon") == []


def test_index_is_rebuilt_for_an_older_library(tmp_path, library):
    con = sqlite3.connect(library.database)
    con.execute("DELETE FROM recipe_search")
    con.commit()
    con.close()
    assert titles(Library(library.database).search("crisp")) == ["Apple-Cranberry Crisp"]


def test_duplicates_by_address_or_by_title_and_ingredients(library):
    cream, crisp = library.get(1), library.get(2)
    same_url = crisp.model_copy(update={"id": None, "title": "Something Else", "source": Source(
        kind="web", url="http://www.example.com/maple-whipped-cream/?utm_source=x")})
    assert [d.id for d in library.find_duplicates(same_url)] == [1]
    retyped = crisp.model_copy(update={"id": None, "title": "Apple Cranberry Crisp with Pecan-Oat Topping"})
    assert [d.id for d in library.find_duplicates(retyped)] == [2]
    same_name_other_dish = cream.model_copy(update={"id": None, "title": crisp.title, "source": Source()})
    assert library.find_duplicates(same_name_other_dish) == []
    assert library.find_duplicates(crisp) == []  # a recipe is not its own duplicate
