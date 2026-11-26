from fractions import Fraction as F

import pytest

from recipebook.style.parser import parse_ingredient_line as parse


@pytest.mark.parametrize("line, text", [
    ("2 tbsp butter, softened", "2 tablespoons butter, softened"),
    ("1 Tbsp. olive oil", "1 tablespoon olive oil"),
    ("1 T sugar", "1 tablespoon sugar"),
    ("1 t salt", "1 teaspoon salt"),
    ("1/2 c. milk", "½ cup milk"),
    ("1 1/2 cups of flour", "1½ cups flour"),
    ("3 cup flour", "3 cups flour"),
    ("1 cups flour", "1 cup flour"),
    ("8 oz cream cheese", "8 ounces cream cheese"),
    ("1 lb. ground beef", "1 pound ground beef"),
    ("250 g flour", "250 grams flour"),
    ("- 2 cups sugar", "2 cups sugar"),
    ("• ¾ tsp kosher salt", "¾ teaspoon coarse salt"),
    ("pinch of salt", "Pinch of salt"),
    ("1 pinch of salt", "1 pinch salt"),
    ("vanilla ice cream, for serving", "Vanilla ice cream, for serving"),
    ("1 (15-ounce) can pumpkin puree", "1 (15-ounce) can pumpkin puree"),
    ("3 to 4 Tbsp ice water", "3 to 4 tablespoons ice water"),
    ("1 tsp vanilla extract", "1 teaspoon pure vanilla extract"),
    ("1 tsp pure vanilla extract", "1 teaspoon pure vanilla extract"),
    ("4 cups powdered sugar, sifted", "4 cups confectioners’ sugar, sifted"),
    ("2 cloves", "2 cloves"),
])
def test_line_is_rewritten_in_house_style(line, text):
    assert parse(line).text == text


def test_parts_of_a_simple_line():
    ing = parse("8 tablespoons (1 stick) unsalted butter, melted")
    assert (ing.quantity, ing.unit, ing.item, ing.prep) == (F(8), "tablespoon", "unsalted butter", "melted")
    assert ing.optional is False


def test_comma_inside_the_item_is_not_the_prep_split():
    ing = parse("3 pounds firm, tart apples (about 6), such as Granny Smith, peeled, cored, and cut into ½-inch slices")
    assert ing.item == "firm, tart apples"
    assert ing.prep.startswith("such as Granny Smith")
    assert (ing.quantity, ing.unit) == (F(3), "pound")


def test_range_is_kept():
    ing = parse("3-4 tbsp ice water")
    assert (ing.quantity, ing.quantity_max, ing.unit, ing.item) == (F(3), F(4), "tablespoon", "ice water")


def test_no_unit():
    ing = parse("4 large eggs, room temperature")
    assert (ing.quantity, ing.unit, ing.item, ing.prep) == (F(4), None, "large eggs", "room temperature")


def test_unit_word_that_is_really_the_ingredient():
    ing = parse("2 cloves")
    assert (ing.unit, ing.item) == (None, "cloves")
    assert parse("2 cloves garlic, minced").unit == "clove"
    assert parse("¼ teaspoon ground cloves").item == "ground cloves"


def test_can_with_size_note():
    ing = parse("1 can (15 ounces) pure pumpkin purée")
    assert (ing.quantity, ing.unit, ing.item) == (F(1), "can", "pure pumpkin purée")


def test_optional_and_plus_more():
    assert parse("Vanilla ice cream, for serving").optional is True
    assert parse("Chopped parsley (optional)").optional is True
    assert parse("½ cup granulated sugar, plus more for serving").optional is False
    assert parse("3 cups all-purpose flour, plus more for pans").optional is False


def test_pinch_without_amount():
    ing = parse("Pinch of coarse salt")
    assert (ing.quantity, ing.unit, ing.item) == (None, "pinch", "coarse salt")


def test_unit_is_not_matched_inside_a_word():
    assert parse("2 carrots, chopped").unit is None
    assert parse("1 candied orange").unit is None
    assert parse("2 garlic heads").item == "garlic heads"


def test_empty_line():
    assert parse("   ").text == ""
