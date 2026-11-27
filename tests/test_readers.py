import json

import httpx
import pytest
from PIL import Image

import samples
from recipebook.intake.material import ReaderError
from recipebook.intake.ocr import NoOcr
from recipebook.intake.readers import parse_page_range, read_pdf, read_photos, read_url, recipe_data_to_text
from recipebook.render.pdf import render_recipe_pdf

RECIPE_DATA = {
    "@context": "https://schema.org", "@type": ["Recipe"], "name": "Brown-Butter Shortbread",
    "description": "<p>Toasty, one-bowl bars.</p>", "recipeYield": ["16", "16 bars"],
    "prepTime": "PT15M", "totalTime": "PT1H30M",
    "recipeIngredient": ["1 cup butter", "1/2 cup sugar", "2 1/4 cups flour"],
    "recipeInstructions": [
        {"@type": "HowToSection", "name": "Make the dough", "itemListElement": [
            {"@type": "HowToStep", "text": "Brown the butter."}, {"@type": "HowToStep", "text": "Stir in sugar and flour."}]},
        {"@type": "HowToStep", "text": "Bake at 325°F for 35 to 40 minutes."},
    ],
}


class FakeOcr:
    def __init__(self, text="Recognized text"):
        self.text, self.seen = text, []

    def read(self, image):
        self.seen.append(image)
        return f"{self.text} {len(self.seen)}"


def web(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def page(body, graph=None):
    script = f'<script type="application/ld+json">{json.dumps(graph)}</script>' if graph is not None else ""
    return f"<html><head>{script}</head><body><nav>Menu</nav><article>{body}</article><footer>Legal</footer></body></html>"


def test_url_with_embedded_recipe_data(tmp_path):
    html = page("<h1>ignored</h1>", {"@graph": [{"@type": "WebSite"}, RECIPE_DATA]})
    material = read_url("https://example.com/shortbread", tmp_path, web(lambda r: httpx.Response(200, text=html)))
    assert material.has_recipe_data and material.kind == "url"
    assert material.source.credit() == "Source: example.com/shortbread"
    text = material.text
    assert text.startswith("Brown-Butter Shortbread") and "Toasty, one-bowl bars." in text
    assert "Yield: 16" in text and "Prep time: 15 minutes" in text and "Total time: 1 hour 30 minutes" in text
    assert "1/2 cup sugar" in text and "Make the dough:" in text and "Bake at 325°F" in text
    assert (tmp_path / material.files[0].split("/")[-1]).read_text() == html  # snapshot kept


def test_url_without_recipe_data_falls_back_to_page_text(tmp_path):
    html = page("<h1>Pie</h1>" + "<p>Mix two cups of flour with butter and bake until golden.</p>" * 6, {"@type": "Article"})
    material = read_url("https://example.com/pie", tmp_path, web(lambda r: httpx.Response(200, text=html)))
    assert not material.has_recipe_data
    assert "Pie" in material.text and "Menu" not in material.text and "Legal" not in material.text


def test_url_with_broken_recipe_data_still_reads_the_page(tmp_path):
    html = ('<html><head><script type="application/ld+json">{not json</script></head><body><article>'
            + "<p>Mix two cups of flour with butter and bake until golden.</p>" * 6 + "</article></body></html>")
    assert "flour" in read_url("https://example.com/x", tmp_path, web(lambda r: httpx.Response(200, text=html))).text


@pytest.mark.parametrize("handler, phrase", [
    (lambda r: httpx.Response(403, text="no"), "refused the request (error 403)"),
    (lambda r: httpx.Response(200, text="<html><body>Sign in</body></html>"), "almost no readable text"),
])
def test_url_failures_carry_advice(tmp_path, handler, phrase):
    with pytest.raises(ReaderError) as error:
        read_url("https://example.com/x", tmp_path, web(handler))
    assert phrase in str(error.value) and "save it as a PDF" in error.value.advice


def test_url_timeout_and_bad_address(tmp_path):
    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ReaderError, match="took too long"):
        read_url("https://example.com/x", tmp_path, web(slow))
    for bad in ("ftp://example.com/x", "pie recipe", "file:///etc/passwd"):
        with pytest.raises(ReaderError, match="not a web address"):
            read_url(bad, tmp_path, web(lambda r: httpx.Response(200)))


def test_recipe_data_plain_string_instructions():
    text = recipe_data_to_text({"name": "Tea", "recipeIngredient": ["1 tea bag"], "recipeInstructions": "Boil water.\nSteep."})
    assert text.endswith("Directions:\nBoil water.\nSteep.")


def test_pdf_with_text_layer_needs_no_ocr(tmp_path):
    pdf = tmp_path / "crisp.pdf"
    pdf.write_bytes(render_recipe_pdf(samples.medium())[0])
    ocr = FakeOcr()
    material = read_pdf(pdf, tmp_path / "originals", ocr)
    assert "Apple-Cranberry Crisp" in material.text and "old-fashioned rolled oats" in material.text
    assert ocr.seen == [] and len(material.images) == 1 and material.files == [str(pdf)]
    assert Image.open(material.images[0]).format == "JPEG"


def scanned_pdf(path, pages):
    sheets = [Image.new("RGB", (600, 800), "white") for _ in range(pages)]
    sheets[0].save(path, "PDF", save_all=True, append_images=sheets[1:])
    return path


def test_scanned_pdf_goes_through_ocr_page_by_page(tmp_path):
    ocr = FakeOcr("Page")
    material = read_pdf(scanned_pdf(tmp_path / "scan.pdf", 3), tmp_path / "originals", ocr, pages="2-3")
    assert material.text == "Page 1\n\nPage 2" and len(material.images) == 2 and len(ocr.seen) == 2


def test_pdf_page_limit_and_ranges(tmp_path):
    pdf = scanned_pdf(tmp_path / "book.pdf", 12)
    with pytest.raises(ReaderError, match="12 pages") as error:
        read_pdf(pdf, tmp_path / "o", FakeOcr())
    assert "page range" in error.value.advice
    assert len(read_pdf(pdf, tmp_path / "o", FakeOcr(), pages="3-12").images) == 10
    assert parse_page_range("", 3) == [0, 1, 2] and parse_page_range("2", 5) == [1] and parse_page_range("2 – 4", 5) == [1, 2, 3]
    for bad in ("0-2", "4-2", "2-9", "two"):
        with pytest.raises(ReaderError):
            parse_page_range(bad, 5)


def test_not_a_pdf(tmp_path):
    fake = tmp_path / "x.pdf"
    fake.write_text("hello")
    with pytest.raises(ReaderError, match="could not be opened as a PDF"):
        read_pdf(fake, tmp_path / "o", FakeOcr())


def test_photos_are_rotated_joined_and_kept(tmp_path):
    first, second = tmp_path / "IMG_1.png", tmp_path / "IMG_2.jpg"
    Image.new("RGB", (4000, 3000), "white").save(first)
    sideways = Image.new("RGB", (400, 300), "white")
    exif = sideways.getexif()
    exif[0x0112] = 6  # camera held sideways
    sideways.save(second, exif=exif)
    material = read_photos([first, second], tmp_path / "originals", FakeOcr("Side"))
    assert material.text == "Side 1\n\nSide 2" and material.files == [str(first), str(second)]
    big, turned = (Image.open(p) for p in material.images)
    assert max(big.size) == 2000 and turned.size == (300, 400)


def test_photo_without_ocr_still_yields_images_for_claude(tmp_path):
    photo = tmp_path / "card.png"
    Image.new("RGB", (300, 200), "white").save(photo)
    material = read_photos([photo], tmp_path / "originals", NoOcr())
    assert material.text == "" and len(material.images) == 1 and material.low_text()
    assert "needs macOS" in material.warnings[0]


def test_unreadable_photo(tmp_path):
    bad = tmp_path / "x.jpg"
    bad.write_text("not an image")
    with pytest.raises(ReaderError, match="could not be opened as an image"):
        read_photos([bad], tmp_path / "o", FakeOcr())
