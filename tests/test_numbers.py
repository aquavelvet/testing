from fractions import Fraction as F

import pytest

from recipebook.style.numbers import (
    find_numbers, format_quantity, format_range, normalize_fractions, parse_quantity_prefix,
)


@pytest.mark.parametrize("text, quantity, upper, rest", [
    ("2 cups flour", F(2), None, "cups flour"),
    ("1/2 cup sugar", F(1, 2), None, "cup sugar"),
    ("1 1/2 cups milk", F(3, 2), None, "cups milk"),
    ("1-1/2 cups milk", F(3, 2), None, "cups milk"),
    ("1½ cups milk", F(3, 2), None, "cups milk"),
    ("1 ½ cups milk", F(3, 2), None, "cups milk"),
    ("¾ teaspoon salt", F(3, 4), None, "teaspoon salt"),
    ("0.5 cup oil", F(1, 2), None, "cup oil"),
    (".25 cup oil", F(1, 4), None, "cup oil"),
    ("0.33 cup oil", F(1, 3), None, "cup oil"),
    ("3 to 4 tablespoons ice water", F(3), F(4), "tablespoons ice water"),
    ("3-4 tablespoons ice water", F(3), F(4), "tablespoons ice water"),
    ("2–3 carrots", F(2), F(3), "carrots"),
    ("250 g flour", F(250), None, "g flour"),
    ("Pinch of salt", None, None, "Pinch of salt"),
])
def test_parse_quantity_prefix(text, quantity, upper, rest):
    assert parse_quantity_prefix(text) == (quantity, upper, rest)


def test_a_falling_range_is_not_a_range():
    # "9-by-13" style text or "2 - 1" must not be read as a range
    quantity, upper, _ = parse_quantity_prefix("4-2 something")
    assert (quantity, upper) == (F(4), None)


@pytest.mark.parametrize("value, text", [
    (F(1, 2), "½"), (F(3, 2), "1½"), (F(2), "2"), (F(1, 3), "⅓"), (F(2, 3), "⅔"),
    (F(9, 4), "2¼"), (F(7, 8), "⅞"), (F(7, 10), "0.7"), (F(5, 12), "5/12"), (F(17, 12), "1 5/12"),
])
def test_format_quantity(value, text):
    assert format_quantity(value) == text


def test_format_range():
    assert format_range(F(3), F(4)) == "3 to 4"
    assert format_range(F(1, 2), None) == "½"
    assert format_range(None, None) == ""


@pytest.mark.parametrize("before, after", [
    ("cut into 1/2-inch slices", "cut into ½-inch slices"),
    ("add 1 1/2 cups", "add 1½ cups"),
    ("a 9-by-13-inch dish", "a 9-by-13-inch dish"),
    ("on 11/26 we baked", "on 11/26 we baked"),
    ("and/or", "and/or"),
    ("3/4 cup and 2/3 cup", "¾ cup and ⅔ cup"),
])
def test_normalize_fractions(before, after):
    assert normalize_fractions(before) == after


def test_find_numbers_treats_typed_and_printed_fractions_alike():
    assert find_numbers("1 1/2 cups at 350°F in a 9x13 pan") == [F(3, 2), F(350), F(9), F(13)]
    assert find_numbers("1½ cups") == find_numbers("1.5 cups") == [F(3, 2)]
