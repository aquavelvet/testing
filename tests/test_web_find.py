import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import samples
from recipebook.config import Home
from recipebook.intake.inbox import InboxWatcher
from recipebook.intake.jobs import JobStore
from recipebook.library import Library
from recipebook.secrets import MemoryStore
from recipebook.web.app import create_app

from test_pipeline import FakeStructurer
from test_readers import FakeOcr, RECIPE_DATA, page


@pytest.fixture
def ctx(tmp_path):
    home = Home(tmp_path / "RecipeBook").ensure()
    library = Library(home.database)
    for recipe in (samples.short(), samples.medium(), samples.long()):
        library.save(recipe.model_copy(update={"id": None}))  # 1 cream, 2 crisp, 3 cake
    structurers = {"local": FakeStructurer(), "claude": FakeStructurer()}
    web = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page("x", RECIPE_DATA))))
    app = create_app(home, ocr=FakeOcr(), key_store=MemoryStore(), structurer_for=lambda n: structurers[n],
                     url_client=web, start_worker=False)
    return TestClient(app, base_url="http://127.0.0.1:8765", follow_redirects=False), app, home, library


def test_library_search_page_and_fragment(ctx):
    client, _, _, _ = ctx
    home_page = client.get("/").text
    assert 'type="search"' in home_page and "3 recipes" in home_page
    found = client.get("/?q=cranberries").text
    assert "1 match for “cranberries”" in found and "Apple-Cranberry Crisp" in found and "Maple Whipped Cream" not in found
    fragment = client.get("/search?q=maple").text
    assert "<html" not in fragment and "2 matches" in fragment and fragment.index("Maple Whipped Cream") < fragment.index("Pumpkin")
    assert "No. 2" in client.get("/search?q=%232").text
    assert "Nothing matches" in client.get("/search?q=anchovy").text
    assert "Desserts &amp; Baking" in client.get("/search?q=").text  # empty search is the normal library


def test_ingredient_list_by_recipe_numbers(ctx):
    client, _, _, _ = ctx
    blank = client.get("/ingredients").text
    assert "No book has been exported yet" in blank
    result = client.get("/ingredients?mode=numbers&entry=3,+2,+1,+77").text
    assert "For 3 recipes" in result and "No recipe numbered 77; skipped." in result
    assert "<strong>all-purpose flour</strong>: 3¾ cups + 2 tablespoons" in result and "Nos. 3, 2" in result
    assert "Optional and for serving" in result and "Ingredient list for: No. 3 Pumpkin Layer Cake" in result
    bad = client.get("/ingredients?mode=numbers&entry=two")
    assert bad.status_code == 422 and "is not a number" in bad.text
    none = client.get("/ingredients?mode=numbers&entry=50-52")
    assert none.status_code == 422 and "None of those numbers match a recipe." in none.text


def test_ingredient_list_by_pages_uses_the_chosen_edition(ctx):
    client, _, _, library = ctx
    client.post("/book", data={"title": "First", "notes": "1", "qr": "1"})
    first = library.get_edition(1)
    cake_page = next(int(p) for p, r in first["page_map"].items() if r == 3)
    cream_page = next(int(p) for p, r in first["page_map"].items() if r == 1)
    result = client.get(f"/ingredients?mode=pages&entry={cake_page},{cake_page + 1},{cream_page},1").text
    assert "For 2 recipes" in result and "No recipe on page 1; skipped." in result
    assert "<strong>pure maple syrup</strong>: ¼ cup + 2 tablespoons" in result

    library.delete(1)  # the library changes and a new edition moves the pages
    client.post("/book", data={"title": "Second"})
    assert "latest" in client.get("/ingredients").text
    latest = client.get(f"/ingredients?mode=pages&entry={cream_page}")
    old = client.get(f"/ingredients?mode=pages&entry={cake_page}&edition=1").text
    assert "Pumpkin Layer Cake" in old  # the first edition still resolves its own page numbers
    assert latest.status_code in (200, 422)


def test_review_warns_about_a_probable_duplicate(ctx):
    client, app, _, library = ctx
    library.save(samples.short().model_copy(update={
        "id": None, "title": "Shortbread", "source": samples.short().source.model_copy(
            update={"url": "https://www.example.com/shortbread/"})}))
    client.post("/add", data={"urls": "https://example.com/shortbread"})
    app.state.pipeline.run_pending()
    review = client.get("/drafts/1").text
    assert "This may already be in your library" in review and "No. 4 Shortbread" in review and "You can still save it" in review


def png_bytes():
    data = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(data, "PNG")
    return data.getvalue()


def test_inbox_queues_settled_files_and_leaves_others(tmp_path):
    inbox, originals = tmp_path / "inbox", tmp_path / "originals"
    inbox.mkdir()
    jobs = JobStore(tmp_path / "library.db")
    watcher = InboxWatcher(inbox, originals, jobs, lambda: "claude")
    (inbox / "IMG 0001.png").write_bytes(png_bytes())
    (inbox / "scan.pdf").write_bytes(b"%PDF-1.4 partial")
    (inbox / "notes.txt").write_text("not a recipe file")
    (inbox / ".DS_Store").write_bytes(b"x")
    (inbox / "empty.jpg").write_bytes(b"")
    assert watcher.scan(now=100.0) == []  # first sighting: sizes are only recorded
    assert watcher.scan(now=101.0) == []  # scans are spaced out
    (inbox / "scan.pdf").write_bytes(b"%PDF-1.4 partial and still copying")
    added = watcher.scan(now=106.0)  # the photo has settled; the PDF just changed size
    assert [(j.kind, j.label, j.structurer) for j in added] == [("photo", "IMG 0001.png", "claude")]
    added = watcher.scan(now=112.0)
    assert [(j.kind, j.label) for j in added] == [("pdf", "scan.pdf")]
    assert sorted(p.name for p in inbox.iterdir()) == [".DS_Store", "empty.jpg", "notes.txt"]
    assert len(list(originals.iterdir())) == 2 and all(j.files[0].startswith(str(originals)) for j in jobs.list())
    assert watcher.scan(now=120.0) == []


def test_whole_flow_from_address_to_book_to_ingredient_list(ctx):
    """Add by address, review, save, search, export the book, and ask for an ingredient list by page."""
    client, app, home, library = ctx
    client.post("/add", data={"urls": "https://example.com/shortbread"})
    app.state.pipeline.run_pending()
    saved = client.post("/drafts/1", data={
        "title": "Brown-Butter Shortbread", "category": "Desserts & Baking", "yield_label": "Makes", "yield_value": "16",
        "ingredients": "1 cup butter\n1/2 cup sugar\n2 1/4 cups flour", "directions": "Bake at 325°F for 35-40 minutes.",
        "source_kind": "web", "source_url": "https://example.com/shortbread", "tags": "Make-ahead"})
    assert saved.headers["location"] == "/recipes/4?saved=1"
    assert "Brown-Butter Shortbread" in client.get("/search?q=shortbread").text
    assert "Brown-Butter Shortbread" in client.get("/search?q=make-ahead").text
    made = client.post("/book", data={"title": "Family Table", "notes": "1", "qr": "1"})
    edition = library.get_edition(int(made.headers["location"].split("=")[1]))
    assert edition["recipe_count"] == 4 and (home.exports / edition["file"]).is_file()
    shortbread_page = next(p for p, r in edition["page_map"].items() if r == 4)
    crisp_page = next(p for p, r in edition["page_map"].items() if r == 2)
    result = client.get(f"/ingredients?entry={shortbread_page},{crisp_page}").text
    assert "For 2 recipes" in result and "<strong>granulated sugar</strong>: ½ cup" in result
    assert "<strong>sugar</strong>: ½ cup" in result and "Nos. 4, 2" not in result.split("granulated sugar")[1][:60]
