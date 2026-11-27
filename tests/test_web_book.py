import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

import samples
from recipebook.config import Home
from recipebook.library import Library
from recipebook.secrets import MemoryStore
from recipebook.web.app import create_app


@pytest.fixture
def ctx(tmp_path):
    home = Home(tmp_path / "RecipeBook").ensure()
    library = Library(home.database)
    for recipe in (samples.short(), samples.medium(), samples.long()):
        library.save(recipe.model_copy(update={"id": None}))
    app = create_app(home, key_store=MemoryStore(), start_worker=False)
    return TestClient(app, base_url="http://127.0.0.1:8765", follow_redirects=False), home, library


def test_export_book_records_an_edition(ctx):
    client, home, library = ctx
    form = client.get("/book").text
    assert "3 saved recipes" in form and "Editions" not in form
    response = client.post("/book", data={
        "title": "Test Kitchen", "edition": "2026 Edition", "binding": "ring", "notes": "1", "qr": "1",
        "categories": ["Desserts & Baking", "Main Dishes"]})
    assert response.headers["location"] == "/book?made=1"
    done = client.get("/book?made=1").text
    assert "Test Kitchen</strong> is ready" in done and "3 recipes" in done and "latest" in done
    assert 'value="ring" selected' in done and 'value="Test Kitchen"' in done  # choices are remembered
    [edition] = library.editions()
    assert edition["binding"] == "ring" and edition["recipe_count"] == 3
    assert sorted(set(edition["page_map"].values())) == [1, 2, 3]
    saved = list(home.exports.glob("test-kitchen-*.pdf"))
    assert len(saved) == 1 and saved[0].name == edition["file"]
    pdf = client.get("/editions/1/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content == saved[0].read_bytes()
    assert len(pdfium.PdfDocument(pdf.content)) == edition["pages"]
    assert client.get("/editions/1/pdf?download=1").headers["content-disposition"].startswith("attachment")


def test_empty_selection_is_explained(ctx):
    client, _, library = ctx
    response = client.post("/book", data={"title": "Holiday", "tag": "Easter"})
    assert response.status_code == 422 and "nothing to put in the book" in response.text
    assert library.editions() == []


def test_missing_edition_file(ctx):
    client, home, _ = ctx
    assert client.get("/editions/9/pdf").status_code == 404
    client.post("/book", data={"title": "Gone"})
    for path in home.exports.glob("*.pdf"):
        path.unlink()
    assert client.get("/editions/1/pdf").status_code == 404


def test_unchecking_every_category_is_refused(ctx):
    client, _, library = ctx
    response = client.post("/book", data={"title": "Nothing", "categories_shown": "1"})
    assert response.status_code == 422 and "Pick at least one category" in response.text
    assert library.editions() == []
    assert 'name="categories_shown"' in client.get("/book").text
