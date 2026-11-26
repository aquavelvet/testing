import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from recipebook.config import Home
from recipebook.intake.structure import StructurerUnavailable
from recipebook.secrets import MemoryStore
from recipebook.web.app import create_app, glossary_from_text, glossary_to_text

from test_pipeline import FakeStructurer
from test_readers import FakeOcr, RECIPE_DATA, page


@pytest.fixture
def ctx(tmp_path):
    home = Home(tmp_path / "RecipeBook")
    structurers = {"local": FakeStructurer(), "claude": FakeStructurer()}
    keys = MemoryStore()
    web = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page("x", RECIPE_DATA))))
    app = create_app(home, ocr=FakeOcr("1 cup butter ¾ cup sugar 325 35 40"), key_store=keys,
                     structurer_for=lambda name: structurers[name], url_client=web, start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1:8765", follow_redirects=False)
    return client, app, structurers, keys, home


def png(name="IMG_1.png"):
    data = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(data, "PNG")
    return ("files", (name, data.getvalue(), "image/png"))


def run(app):
    app.state.pipeline.run_pending()


def test_add_url_review_and_save(ctx):
    client, app, _, _, _ = ctx
    response = client.post("/add", data={"urls": "https://example.com/shortbread\n\n", "structurer": "local"})
    assert response.headers["location"] == "/queue"
    queue = client.get("/queue").text
    assert "Queued" in queue and 'http-equiv="refresh"' in queue
    run(app)
    queue = client.get("/queue").text
    assert "Done" in queue and 'href="/drafts/1"' in queue and "1 to check" in queue
    assert 'http-equiv="refresh"' not in queue and '<span class="badge">1</span>' in queue

    review = client.get("/drafts/1").text
    assert "Review: Shortbread" in review and "Read by the local model" in review
    assert "¾ does not appear in the original" in review  # fidelity flag: source says 1/2 cup sugar
    assert "1/2 cup sugar" in review  # original text shown beside the form
    assert "1 cup butter" in review and "Bake at 325 degrees for 35 to 40 minutes." in review

    form = {"title": "Shortbread", "category": "Desserts & Baking", "ingredients": "1 cup butter\n1/2 cup sugar",
            "directions": "Bake at 325 degrees for 35 to 40 minutes.", "source_kind": "web",
            "source_url": "https://example.com/shortbread"}
    checked = client.post("/drafts/1", data={**form, "action": "check"})
    assert checked.headers["location"] == "/drafts/1"
    rechecked = client.get("/drafts/1").text
    assert "does not appear in the original" not in rechecked  # the fix cleared the warning
    assert "Numbers in the original that are not in the recipe" in rechecked  # the yield and times are still missing

    saved = client.post("/drafts/1", data=form)
    assert saved.headers["location"] == "/recipes/1?saved=1"
    recipe = client.get("/recipes/1").text
    assert "½ cup sugar" in recipe and "No. 1" in recipe
    assert client.get("/drafts/1").headers["location"] == "/recipes/1"
    queue = client.get("/queue").text
    assert "Saved" in queue and "badge" not in queue


def test_draft_cannot_be_saved_incomplete(ctx):
    client, app, _, _, _ = ctx
    client.post("/add", data={"urls": "https://example.com/shortbread"})
    run(app)
    response = client.post("/drafts/1", data={"title": "Shortbread", "category": "Desserts & Baking",
                                              "ingredients": "", "directions": "Bake."})
    assert response.status_code == 422 and "Still needed: ingredients" in response.text
    assert "No recipes yet" in client.get("/").text


def test_photos_one_recipe_or_each_and_cookbook_credit(ctx):
    client, app, structurers, _, home = ctx
    client.post("/add", files=[png("a.png"), png("b.png")], data={"one_recipe": "1", "cookbook_title": "Sample Cookbook"})
    client.post("/add", files=[png("c.png"), png("d.png")], data={})
    jobs = app.state.jobs.list()
    assert sorted(len(j.files) for j in jobs) == [1, 1, 2]
    assert [j.label for j in jobs if len(j.files) == 2] == ["a.png and 1 more"]
    run(app)
    assert len(structurers["local"].seen) == 3
    drafts = [d for j in jobs for d in app.state.jobs.drafts_for(j.id)]
    credits = sorted(d.recipe.source.credit() for d in drafts)
    assert credits == ["", "", "Source: Sample Cookbook"]
    review = client.get(f"/drafts/{drafts[0].id}").text
    assert 'src="/originals/' in review
    name = review.split('src="/originals/')[1].split('"')[0]
    image = client.get(f"/originals/{name}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"


def test_add_rejects_nothing_and_wrong_file_types(ctx):
    client, _, _, _, _ = ctx
    empty = client.post("/add", data={"urls": "  "})
    assert empty.status_code == 422 and "Paste at least one web address" in empty.text
    wrong = client.post("/add", files=[("files", ("notes.docx", b"x", "application/octet-stream"))])
    assert wrong.status_code == 422 and "not photos or PDFs: notes.docx" in wrong.text


def test_failed_job_shows_reason_and_retry_with_claude(ctx):
    client, app, structurers, keys, _ = ctx
    structurers["local"].result = []
    client.post("/add", data={"urls": "https://example.com/shortbread"})
    run(app)
    queue = client.get("/queue").text
    assert "Failed" in queue and "No recipe was found in this item." in queue
    assert "Retry with Claude" in queue and "disabled" in queue  # no key yet
    keys.set("sk-test")
    assert "disabled" not in client.get("/queue").text
    assert client.post("/jobs/1/retry", data={"structurer": "claude"}).headers["location"] == "/queue"
    run(app)
    assert len(structurers["claude"].seen) == 1 and app.state.jobs.get(1).state == "done"
    assert "Read by Claude" not in client.get("/drafts/1").text  # the fake reports itself as local
    assert "Claude" in client.get("/queue").text


def test_waiting_banner_when_ollama_is_down(ctx):
    client, app, structurers, _, _ = ctx
    structurers["local"].error = StructurerUnavailable("Ollama is not running.", "Open the Ollama app, or run:  ollama serve")
    client.post("/add", data={"urls": "https://example.com/shortbread"})
    run(app)
    queue = client.get("/queue").text
    assert "Ollama is not running." in queue and "ollama serve" in queue and "start by themselves" in queue
    assert 'http-equiv="refresh"' in queue


def test_discard_and_remove(ctx):
    client, app, _, _, home = ctx
    client.post("/add", files=[png()], data={})
    run(app)
    assert client.post("/drafts/1/discard").headers["location"] == "/queue"
    assert "Discarded" in client.get("/queue").text and app.state.jobs.needing_review() == 0
    kept = list(home.originals.iterdir())
    client.post("/jobs/1/delete")
    assert "Nothing has been added yet" in client.get("/queue").text
    assert list(home.originals.iterdir()) == kept  # originals are never deleted automatically
    assert client.get("/drafts/1").status_code == 404 and client.post("/jobs/1/retry").status_code == 404


def test_originals_cannot_escape_their_folder(ctx):
    client, _, _, _, home = ctx
    (home.root / "library.db").exists()
    assert client.get("/originals/..%2Flibrary.db").status_code == 404
    assert client.get("/originals/nope.jpg").status_code == 404
    (home.originals / "snap.html").write_text("<script>alert(1)</script>")
    snapshot = client.get("/originals/snap.html")
    assert snapshot.headers["content-type"].startswith("text/plain") and snapshot.headers["x-content-type-options"] == "nosniff"


def test_settings_round_trip(ctx):
    client, _, _, keys, _ = ctx
    page_html = client.get("/settings").text
    assert "No key saved" in page_html and "qwen2.5:7b" in page_html and "coarse salt: kosher salt" in page_html
    names = ["Breakfast & Brunch", "Starters & Soups", "Main Dishes", "Salads & Sides", "Sweets & Breads"]
    response = client.post("/settings", data={
        "category": names, "glossary": "coarse salt: kosher salt, rock salt\n\nscallions: green onions",
        "local_model": "llama3.1:8b", "default_structurer": "claude", "claude_key": " sk-ant-secret "})
    assert response.headers["location"] == "/settings?saved=1"
    page_html = client.get("/settings?saved=1").text
    assert "Sweets &amp; Breads" in page_html and "llama3.1:8b" in page_html and "A key is saved" in page_html
    assert "sk-ant-secret" not in page_html and keys.get() == "sk-ant-secret"
    assert "scallions: green onions" in page_html and "rock salt" in page_html
    assert 'value="claude" checked' in client.get("/add").text
    client.post("/settings", data={"category": names, "glossary": "", "clear_key": "1", "claude_key": "ignored"})
    assert keys.get() is None
    bad = client.post("/settings", data={"category": names[:4] + [""], "glossary": ""})
    assert bad.status_code == 422 and "five different names" in bad.text


def test_glossary_text_round_trip():
    entries = glossary_from_text("coarse salt: kosher salt, rock salt\nParmesan:\n\n : orphan")
    assert [(e.preferred, e.variants) for e in entries] == [("coarse salt", ("kosher salt", "rock salt")), ("Parmesan", ())]
    assert glossary_from_text(glossary_to_text(entries)) == entries
