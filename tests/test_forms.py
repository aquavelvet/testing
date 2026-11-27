from recipebook.web.forms import (
    form_from_recipe, ingredients_to_text, parse_ingredients, parse_steps, recipe_from_form, steps_to_text,
)

from samples import medium


def test_ingredient_groups_from_text():
    groups = parse_ingredients("For the crust:\n1 cup flour\n\n2 tbsp sugar\nFor the filling:\n3 apples\n")
    assert [(g.name, [i.text for i in g.items]) for g in groups] == [
        ("For the crust", ["1 cup flour", "2 tbsp sugar"]),
        ("For the filling", ["3 apples"]),
    ]


def test_ungrouped_ingredients_and_empty_headings():
    assert [(g.name, len(g.items)) for g in parse_ingredients("1 cup flour\n2 eggs")] == [(None, 2)]
    assert parse_ingredients("For nothing:\n") == []
    assert parse_ingredients("") == []


def test_steps_by_paragraph_with_lead_ins_and_numbering():
    steps = parse_steps("1. Preheat oven to 350 degrees.\n\nMake the topping: Stir together\nflour and oats.\n\n3) Bake.")
    assert [(s.lead, s.text) for s in steps] == [
        (None, "Preheat oven to 350 degrees."),
        ("Make the topping", "Stir together flour and oats."),
        (None, "Bake."),
    ]


def test_steps_by_line_when_no_blank_lines():
    assert [s.text for s in parse_steps("Step 1: Mix.\nStep 2: Bake.")] == ["Mix.", "Bake."]


def test_a_long_sentence_with_a_colon_is_not_a_lead_in():
    steps = parse_steps("Whisk together the following ingredients in a large bowl until smooth: flour, sugar, salt.")
    assert steps[0].lead is None


def test_text_round_trip():
    recipe = medium()
    assert parse_ingredients(ingredients_to_text(recipe.ingredient_groups))[1].name == "For the filling"
    again = parse_steps(steps_to_text(recipe.steps))
    assert [(s.lead, s.text) for s in again] == [(s.lead, s.text) for s in recipe.steps]


def test_recipe_form_round_trip():
    recipe = medium()
    form = form_from_recipe(recipe)
    assert form["total_time"] == "1 hour 45 minutes"
    rebuilt = recipe_from_form(form, existing=recipe)
    assert rebuilt.id == recipe.id
    assert rebuilt.total_minutes == 105
    assert [i.text for i in rebuilt.ingredients()] == [i.text for i in recipe.ingredients()]
    assert rebuilt.source.label == "Handwritten family recipe card"


def test_new_recipe_from_form():
    recipe = recipe_from_form({
        "title": " Toast ", "ingredients": "2 slices bread", "directions": "Toast the bread.",
        "category": "Breakfast & Brunch", "tags": "Quick, , Weekday", "yield_label": "Makes", "yield_value": "2",
        "active_time": "5", "source_kind": "web", "source_url": "https://example.com/toast",
    })
    assert recipe.title == "Toast" and recipe.id is None
    assert recipe.tags == ["Quick", "Weekday"]
    assert recipe.yield_label == "Makes" and recipe.active_minutes == 5 and recipe.total_minutes is None
    assert recipe.source.credit() == "Source: example.com/toast"
