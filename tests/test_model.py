from fractions import Fraction as F

from recipebook.model import Ingredient, Recipe, Source, format_minutes, parse_minutes


def test_fractions_survive_json():
    ing = Ingredient(text="⅓ cup oil", quantity=F(1, 3), unit="cup", item="oil")
    again = Ingredient.model_validate_json(ing.model_dump_json())
    assert again.quantity == F(1, 3)


def test_source_credit():
    assert Source(kind="web", url="https://www.example.com/pie/").credit() == "Source: example.com/pie"
    assert Source(kind="cookbook", title="Sample Cookbook", author="A. N. Author", page="112").credit() == \
        "Source: Sample Cookbook, by A. N. Author, page 112"
    assert Source(kind="cookbook", title="Sample Cookbook").credit() == "Source: Sample Cookbook"
    assert Source(kind="other", label="Handwritten family recipe card").credit() == "Source: Handwritten family recipe card"
    assert Source().credit() == ""


def test_minutes():
    assert format_minutes(45) == "45 minutes"
    assert format_minutes(60) == "1 hour"
    assert format_minutes(105) == "1 hour 45 minutes"
    assert format_minutes(180) == "3 hours"
    assert format_minutes(1) == "1 minute"
    assert format_minutes(None) == ""
    assert parse_minutes("1 hour 45 minutes") == 105
    assert parse_minutes("1h 45m") == 105
    assert parse_minutes("1:45") == 105
    assert parse_minutes("25") == 25
    assert parse_minutes("3 hrs") == 180
    assert parse_minutes("") is None
    assert parse_minutes("soon") is None
    assert parse_minutes("1 1/2 hours") == 90
    assert parse_minutes("1½ hours") == 90
    assert parse_minutes("1/2 hour") == 30
    assert parse_minutes("1.5 hours") == 90
    assert parse_minutes("2 hours 15 min") == 135


def test_missing_for_save():
    assert Recipe(title="").missing_for_save() == ["title", "ingredients", "directions"]
