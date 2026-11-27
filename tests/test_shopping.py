import pytest

import samples
from recipebook.model import Ingredient, IngredientGroup, Recipe, Step
from recipebook.shopping import EntryError, merge, parse_numbers, recipes_on_pages
from recipebook.style.housestyle import apply_house_style


def recipe(number, *lines):
    return apply_house_style(Recipe(id=number, title=f"R{number}", steps=[Step(text="Cook.")],
                                    ingredient_groups=[IngredientGroup(items=[Ingredient(text=l) for l in lines])]))


def lines(merged):
    return [line.text() for line in merged.needed]


def test_parse_numbers():
    assert parse_numbers("34, 36-37") == [34, 36, 37]
    assert parse_numbers(" 118 142;157  #3 ") == [118, 142, 157, 3]
    assert parse_numbers("5, 5, 4-6") == [5, 4, 6]
    assert parse_numbers("36–37") == [36, 37]
    for bad in ("", "abc", "7-3", "1-9999", "3.5"):
        with pytest.raises(EntryError):
            parse_numbers(bad)


def test_pages_resolve_through_an_edition():
    page_map = {"34": 118, "35": 118, "36": 142, "37": 157}
    assert recipes_on_pages(page_map, [34, 35, 36]) == ([118, 142], [])  # both pages of a spread are one recipe
    assert recipes_on_pages(page_map, [33, 37, 90]) == ([157], [33, 90])  # divider and out-of-range pages are skipped


def test_same_unit_is_added_and_different_units_sit_side_by_side():
    merged = merge([recipe(1, "3 cups all-purpose flour", "1 tsp salt"),
                    recipe(2, "3/4 cup AP flour", "2 tablespoons all-purpose flour", "1/2 teaspoon salt")])
    assert lines(merged) == ["all-purpose flour: 3¾ cups + 2 tablespoons (Nos. 1, 2)", "salt: 1½ teaspoons (Nos. 1, 2)"]


def test_counts_ranges_and_pinches():
    merged = merge([recipe(1, "4 large eggs", "3 to 4 tablespoons ice water", "Pinch of coarse salt"),
                    recipe(2, "2 large eggs", "2 tablespoons ice water", "1 teaspoon kosher salt")])
    assert lines(merged) == ["coarse salt: 1 teaspoon + a pinch (Nos. 1, 2)", "ice water: 5 to 6 tablespoons (Nos. 1, 2)",
                             "large eggs: 6 (Nos. 1, 2)"]


def test_singular_and_plural_units():
    assert lines(merge([recipe(1, "1/2 cup sugar"), recipe(2, "1/2 cup sugar")])) == ["sugar: 1 cup (Nos. 1, 2)"]
    assert lines(merge([recipe(1, "1/4 cup sugar"), recipe(2, "1/2 cup sugar")])) == ["sugar: ¾ cup (Nos. 1, 2)"]
    assert lines(merge([recipe(1, "1 can (15 ounces) pumpkin"), recipe(2, "1 can pumpkin")])) == ["pumpkin: 2 cans (Nos. 1, 2)"]


def test_optional_items_and_bare_mentions():
    merged = merge([recipe(1, "Vanilla ice cream, for serving", "Cooking spray")])
    assert lines(merged) == ["cooking spray (No. 1)"]
    assert [l.text() for l in merged.optional] == ["vanilla ice cream (No. 1)"]


def test_real_samples_merge_and_print():
    cake, crisp, cream = samples.long(), samples.medium(), samples.short()
    merged = merge([cake, crisp, cream])
    by_item = {line.item: line.text() for line in merged.needed}
    assert by_item["all-purpose flour"] == "all-purpose flour: 3¾ cups + 2 tablespoons (Nos. 118, 142)"
    assert by_item["unsalted butter"] == "unsalted butter: 1½ cups + 8 tablespoons (Nos. 118, 142)"
    assert by_item["pure maple syrup"] == "pure maple syrup: ¼ cup + 2 tablespoons (Nos. 118, 157)"
    assert by_item["coarse salt"].startswith("coarse salt: 1¼ teaspoons + a pinch")
    text = merged.text([cake, crisp, cream])
    assert text.startswith("Ingredient list for: No. 118 Pumpkin Layer Cake")
    assert "Optional and for serving:\nvanilla ice cream (No. 142)" in text
