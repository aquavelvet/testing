import pypdfium2 as pdfium
import pytest
from fontTools.ttLib import TTFont

import samples
from recipebook.model import Ingredient, IngredientGroup, Recipe, Step
from recipebook.render.pdf import BINDINGS, FONTS, lay_out, recipe_html, render_recipe_pdf
from recipebook.style.numbers import UNICODE_FRACTIONS

A5_PT = (419.5, 595.3)
MM = 96 / 25.4  # WeasyPrint lays out in CSS pixels


def text_boxes(document):
    for number, page in enumerate(document.pages, start=1):
        root = page._page_box
        body = [child for child in root.children if type(child).__name__ != "MarginBox"]
        for block in body:
            for box in block.descendants():
                if type(box).__name__ == "TextBox" and box.text.strip():
                    yield number, root, box


def pdf_text(data: bytes) -> list[str]:
    pdf = pdfium.PdfDocument(data)
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


def squash(text: str) -> str:
    """Lowercase with all whitespace removed, so letter-spaced labels can be matched."""
    return "".join(text.split()).lower()


@pytest.mark.parametrize("sample, kind, pages", [
    ("short", "page", 1),
    ("medium", "page", 1),
    ("long", "spread", 2),
])
def test_layout_is_chosen_by_length(sample, kind, pages):
    layout, document = lay_out(getattr(samples, sample)())
    assert (layout.kind, layout.pages) == (kind, pages)
    assert len(document.pages) == pages
    assert 8.0 <= layout.body_pt <= 9.0


def test_short_recipe_uses_full_size_type():
    layout, _ = lay_out(samples.short())
    assert layout.body_pt == 8.5


def test_very_long_recipe_falls_back_to_running_layout():
    layout, document = lay_out(samples.very_long())
    assert layout.kind == "flow" and layout.pages == len(document.pages) >= 3


@pytest.mark.parametrize("sample", ["short", "medium", "long", "very_long"])
@pytest.mark.parametrize("binding", ["none", "bound", "ring"])
def test_no_text_runs_past_the_text_area(sample, binding):
    _, document = lay_out(getattr(samples, sample)(), binding=binding, page_numbers=True)
    for number, root, box in text_boxes(document):
        left = root.content_box_x()
        right = left + root.width
        assert box.position_x >= left - 0.5, f"page {number}: {box.text!r} starts left of the text area"
        assert box.position_x + box.width <= right + 0.5, f"page {number}: {box.text!r} runs past the text area"


@pytest.mark.parametrize("binding", ["none", "bound", "ring"])
def test_every_binding_has_the_same_text_width(binding):
    _, document = lay_out(samples.short(), binding=binding)
    assert document.pages[0]._page_box.width == pytest.approx(120 * MM, abs=0.1)
    assert BINDINGS[binding].inner_mm + BINDINGS[binding].outer_mm == 28


def test_binding_does_not_change_the_layout():
    layouts = {lay_out(samples.medium(), binding=b, page_numbers=True)[0] for b in BINDINGS}
    assert len(layouts) == 1


def test_bound_pages_mirror_their_margins():
    _, document = lay_out(samples.long(), binding="bound", page_numbers=True)
    first, second = (page._page_box for page in document.pages)
    # a lone export starts on a right-hand page: gutter on the left, then mirrored
    assert first.content_box_x() == pytest.approx(17 * MM, abs=0.1)
    assert second.content_box_x() == pytest.approx(11 * MM, abs=0.1)


def test_pdf_is_a5_and_carries_the_recipe():
    data, layout = render_recipe_pdf(samples.medium())
    assert data.startswith(b"%PDF")
    pdf = pdfium.PdfDocument(data)
    assert len(pdf) == layout.pages == 1
    assert pdf[0].get_size() == pytest.approx(A5_PT, abs=0.5)
    text = squash(pdf_text(data)[0])
    for expected in ("Desserts & Baking", "No. 142", "Apple-Cranberry Crisp", "Ingredients", "For the topping",
                     "Directions", "Make the topping:", "1 hour 45 minutes", "Cook’s Note",
                     "Source: Handwritten family recipe card"):
        assert squash(expected) in text, expected


def test_spread_puts_ingredients_then_directions():
    data, _ = render_recipe_pdf(samples.long())
    left, right = (squash(page) for page in pdf_text(data))
    assert "ingredients" in left and "directions" not in left
    assert "directions" in right and squash("Preheat oven to 350 degrees") in right
    credit = squash("Source: Sample Cookbook, by A. N. Author, page 112")
    assert credit in left and credit in right


def test_page_numbers_only_when_asked():
    without = pdf_text(render_recipe_pdf(samples.short())[0])[0]
    with_numbers = pdf_text(render_recipe_pdf(samples.short(), binding="bound", page_numbers=True)[0])[0]
    assert without.split()[-1] != "1"
    assert with_numbers.split()[-1] == "1" or "\n1" in with_numbers


def test_minimal_recipe_renders_without_optional_parts():
    recipe = Recipe(
        title="Toast <b>& Jam</b>", category="Breakfast & Brunch",
        ingredient_groups=[IngredientGroup(items=[Ingredient(text="2 slices bread")])],
        steps=[Step(text="Toast the bread.")],
    )
    html = recipe_html(recipe, "page", 8.5, BINDINGS["none"], False)
    assert "Toast &lt;b&gt;&amp; Jam&lt;/b&gt;" in html
    assert 'class="meta"' not in html and 'class="headnote"' not in html and 'class="note"' not in html
    assert "No. " not in html
    data, layout = render_recipe_pdf(recipe)
    assert layout.pages == 1 and "Toast <b>& Jam</b>" in pdf_text(data)[0]


def test_body_font_has_every_fraction_character():
    for name in ("SourceSerif4-Regular.ttf", "SourceSerif4-Italic.ttf", "SourceSerif4-SemiBold.ttf"):
        cmap = TTFont(FONTS / name).getBestCmap()
        missing = [glyph for glyph in UNICODE_FRACTIONS if ord(glyph) not in cmap]
        assert not missing, f"{name} lacks {missing}"


def test_fonts_ship_with_their_licenses():
    for family in ("CormorantGaramond", "SourceSerif4", "Jost"):
        assert (FONTS / f"OFL-{family}.txt").read_text().count("SIL Open Font License") >= 1
