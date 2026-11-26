from recipebook.model import Ingredient, IngredientGroup, Recipe, Step
from recipebook.style.fidelity import check_fidelity
from recipebook.style.glossary import apply_glossary
from recipebook.style.housestyle import apply_house_style, tidy_text


def test_glossary_replaces_variants():
    assert apply_glossary("kosher salt and powdered sugar") == "coarse salt and confectioners’ sugar"
    assert apply_glossary("packed light brown sugar") == "packed light-brown sugar"
    assert apply_glossary("grated parmesan") == "grated Parmesan"


def test_glossary_does_not_double_apply():
    assert apply_glossary("pure vanilla extract") == "pure vanilla extract"
    assert apply_glossary("vanilla extract") == "pure vanilla extract"
    assert apply_glossary("old-fashioned rolled oats") == "old-fashioned rolled oats"
    assert apply_glossary("rolled oats") == "old-fashioned rolled oats"


def test_glossary_needs_whole_words():
    assert apply_glossary("unwhite sugary") == "unwhite sugary"


def test_tidy_text():
    assert tidy_text("Preheat oven to 350°F.") == "Preheat oven to 350 degrees."
    assert tidy_text("Preheat oven to 350 degrees F.") == "Preheat oven to 350 degrees."
    assert tidy_text("Bake at 180°C.") == "Bake at 180°C."
    assert tidy_text("cut into 1/2-inch  slices") == "cut into ½-inch slices"
    assert tidy_text("don't overbeat") == "don’t overbeat"


def _recipe(**kw):
    base = dict(
        title="Test",
        ingredient_groups=[IngredientGroup(items=[
            Ingredient(text="1½ cups flour"), Ingredient(text="2 tablespoons sugar")])],
        steps=[Step(text="Preheat oven to 350 degrees. Bake 30 to 35 minutes.")],
        yield_value="12",
    )
    base.update(kw)
    return Recipe(**base)


ORIGINAL = "Makes 12. 1 1/2 cups flour, 2 Tbsp sugar. Heat oven to 350°F and bake 30-35 minutes."


def test_fidelity_passes_when_only_wording_changed():
    assert check_fidelity(ORIGINAL, _recipe()) == []


def test_fidelity_flags_a_changed_amount_on_its_line():
    recipe = _recipe(ingredient_groups=[IngredientGroup(items=[
        Ingredient(text="1¾ cups flour"), Ingredient(text="2 tablespoons sugar")])])
    flags = check_fidelity(ORIGINAL, recipe)
    changed = [f for f in flags if f.kind == "amount_changed"]
    assert len(changed) == 1 and changed[0].field == "ingredients.0.0" and "1¾" in changed[0].message
    dropped = [f for f in flags if f.kind == "amount_dropped"]
    assert len(dropped) == 1 and "1½" in dropped[0].message and dropped[0].severity == "info"


def test_fidelity_checks_times():
    ok = _recipe(total_minutes=105)
    assert not [f for f in check_fidelity(ORIGINAL + " Total time: 1 hour 45 minutes.", ok) if f.field == "total_minutes"]
    assert not [f for f in check_fidelity(ORIGINAL + " Total: 105 min.", ok) if f.field == "total_minutes"]
    flags = check_fidelity(ORIGINAL, ok)
    assert [f for f in flags if f.field == "total_minutes" and f.severity == "info"]


def test_fidelity_skipped_without_an_original():
    assert check_fidelity("", _recipe()) == []


def test_house_style_on_a_whole_recipe():
    recipe = Recipe(
        title="  Shortbread ",
        ingredient_groups=[IngredientGroup(name="For the dough:", items=[
            Ingredient(text="1 c butter"), Ingredient(text=""), Ingredient(text="2 1/4 cups AP flour")])],
        steps=[Step(lead="Bake:", text="Heat oven to 325°F."), Step(text="  ")],
        tags=["Fall", "fall ", "Make-ahead"],
    )
    styled = apply_house_style(recipe)
    assert styled.title == "Shortbread"
    assert styled.ingredient_groups[0].name == "For the dough"
    assert [i.text for i in styled.ingredients()] == ["1 cup butter", "2¼ cups all-purpose flour"]
    assert styled.ingredients()[1].item == "all-purpose flour"
    assert [(s.lead, s.text) for s in styled.steps] == [("Bake", "Heat oven to 325 degrees.")]
    assert styled.tags == ["Fall", "Make-ahead"]
