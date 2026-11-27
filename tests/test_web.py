import pytest
from fastapi.testclient import TestClient

from recipebook.cli import doctor
from recipebook.config import Home
from recipebook.web.app import create_app

FORM = {
    "title": "brown-butter shortbread",
    "headnote": "Browning the butter first gives these bars a deep, toasty flavor.",
    "category": "Desserts & Baking",
    "tags": "Fall, Make-ahead",
    "yield_label": "Makes",
    "yield_value": "16",
    "active_time": "15 minutes",
    "total_time": "1h 30m",
    "ingredients": "1 c. unsalted butter, cut into pieces\n1/2 cup white sugar, plus more for sprinkling\n"
                   "1 tsp vanilla extract\n3/4 tsp kosher salt\n2 1/4 cups AP flour",
    "directions": "1. Heat oven to 325°F.\n\n2. Brown the butter: Melt butter over medium heat until golden.\n\n3. Bake 35-40 minutes.",
    "note": "Keeps 1 week.",
    "source_kind": "web",
    "source_url": "https://example.com/brown-butter-shortbread",
}


@pytest.fixture
def home(tmp_path):
    return Home(tmp_path / "RecipeBook")


@pytest.fixture
def client(home):
    return TestClient(create_app(home), base_url="http://127.0.0.1:8765", follow_redirects=False)


def create(client, **changes):
    response = client.post("/recipes", data={**FORM, **changes})
    assert response.status_code == 303, response.text
    return response.headers["location"]


def test_empty_library(client):
    page = client.get("/")
    assert page.status_code == 200 and "No recipes yet" in page.text


def test_create_applies_house_style_and_numbers_the_recipe(client):
    location = create(client)
    assert location == "/recipes/1?saved=1"
    page = client.get(location).text
    assert "No. 1" in page and "Saved." in page
    for line in ("1 cup unsalted butter, cut into pieces", "½ cup granulated sugar, plus more for sprinkling",
                 "1 teaspoon pure vanilla extract", "¾ teaspoon coarse salt", "2¼ cups all-purpose flour"):
        assert line in page, line
    assert "Heat oven to 325 degrees." in page
    assert "Brown the butter: Melt butter" in page
    assert "1 hour 30 minutes" in page
    library = client.get("/").text
    assert "brown-butter shortbread" in library and "1 recipe" in library


def test_missing_fields_are_reported_and_nothing_is_saved(client):
    response = client.post("/recipes", data={**FORM, "ingredients": "", "directions": " "})
    assert response.status_code == 422
    assert "Still needed: ingredients, directions" in response.text
    assert "brown-butter shortbread" in response.text  # what was typed is kept
    assert "No recipes yet" in client.get("/").text


def test_pdf_view_and_export(client, home):
    create(client)
    view = client.get("/recipes/1/pdf")
    assert view.status_code == 200 and view.headers["content-type"] == "application/pdf"
    assert view.content.startswith(b"%PDF") and view.headers["content-disposition"].startswith("inline")
    assert not list(home.exports.glob("*.pdf"))
    export = client.get("/recipes/1/pdf?download=1")
    assert export.headers["content-disposition"] == 'attachment; filename="no-1-brown-butter-shortbread.pdf"'
    assert (home.exports / "no-1-brown-butter-shortbread.pdf").read_bytes() == export.content


def test_preview_does_not_save(client):
    preview = client.post("/recipes/preview", data=FORM)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    assert "No recipes yet" in client.get("/").text
    blank = client.post("/recipes/preview", data={"title": "", "ingredients": "", "directions": ""})
    assert blank.status_code == 200 and blank.content.startswith(b"%PDF")


def test_update_keeps_the_number(client):
    create(client)
    response = client.post("/recipes/1", data={**FORM, "title": "Brown-Butter Shortbread", "recipe_id": "1"})
    assert response.headers["location"] == "/recipes/1?saved=1"
    assert "Brown-Butter Shortbread" in client.get("/recipes/1").text
    bad = client.post("/recipes/1", data={**FORM, "title": " "})
    assert bad.status_code == 422 and "Still needed: title" in bad.text


def test_delete_and_number_is_not_reused(client):
    create(client)
    response = client.post("/recipes/1/delete")
    assert response.headers["location"] == "/?deleted=1"
    assert "Recipe No. 1 was deleted" in client.get("/?deleted=1").text
    assert client.get("/recipes/1").status_code == 404
    assert create(client) == "/recipes/2?saved=1"


def test_unknown_recipe_is_a_friendly_404(client):
    for path in ("/recipes/99", "/recipes/99/pdf"):
        response = client.get(path)
        assert response.status_code == 404 and "There is no recipe No. 99." in response.text
    assert client.post("/recipes/99/delete").status_code == 404


def test_new_recipe_form_lists_the_five_categories(client):
    page = client.get("/recipes/new").text
    for name in ("Breakfast &amp; Brunch", "Starters &amp; Soups", "Main Dishes", "Salads &amp; Sides", "Desserts &amp; Baking"):
        assert name in page


def test_text_typed_into_the_form_is_escaped(client):
    location = create(client, title="<script>alert(1)</script>")
    page = client.get(location).text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_requests_from_other_hosts_are_refused(client):
    assert client.get("/", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/", headers={"host": "localhost:8765"}).status_code == 200


def test_form_posts_from_other_sites_are_refused(client):
    refused = client.post("/recipes", data=FORM, headers={"origin": "https://evil.example"})
    assert refused.status_code == 403
    assert "No recipes yet" in client.get("/").text
    allowed = client.post("/recipes", data=FORM, headers={"origin": "http://127.0.0.1:8765"})
    assert allowed.status_code == 303


def test_doctor_passes_here(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RECIPEBOOK_HOME", str(tmp_path / "RecipeBook"))
    assert doctor() == 0
    assert "FAIL" not in capsys.readouterr().out
