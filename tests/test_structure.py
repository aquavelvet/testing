import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from PIL import Image

from recipebook.intake.material import SourceMaterial
from recipebook.intake.structure import (
    CLAUDE_MODEL, ClaudeStructurer, LocalStructurer, StructurerError, StructurerUnavailable,
    output_schema, system_prompt, user_text,
)
from recipebook.model import DEFAULT_CATEGORIES, Source
from recipebook.style.glossary import DEFAULT_GLOSSARY

DRAFT = {
    "title": "Brown-Butter Shortbread", "headnote": "Toasty one-bowl bars.", "headnote_from_source": False,
    "yield_label": "Makes", "yield_value": "16", "active_minutes": 15, "total_minutes": 90,
    "ingredient_groups": [{"name": None, "items": ["1 cup unsalted butter", "2¼ cups all-purpose flour", " "]}],
    "steps": [{"lead": None, "text": "Preheat oven to 325 degrees."}, {"lead": "Bake", "text": "Bake 35 to 40 minutes."}],
    "note": "", "category": "Desserts & Baking", "tags": ["Make-ahead"], "page_number": "112",
}
REPLY = json.dumps({"recipes": [DRAFT]})
MATERIAL = SourceMaterial(kind="photo", text="Shortbread. 1 cup butter, 2 1/4 cups flour. Bake at 325.",
                          source=Source(kind="cookbook", title="Sample Cookbook"), files=["/o/a.heic"])


def ollama(chat, models=("qwen2.5:7b",)):
    calls = []

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        calls.append(json.loads(request.content))
        return chat(len(calls))

    return LocalStructurer(client=httpx.Client(transport=httpx.MockTransport(handler))), calls


def chat_reply(content):
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def test_schema_is_strict_everywhere():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    schema = output_schema(DEFAULT_CATEGORIES)
    walk(schema)
    assert schema["properties"]["recipes"]["items"]["properties"]["category"]["enum"] == DEFAULT_CATEGORIES


def test_prompt_carries_style_guide_glossary_and_categories():
    prompt = system_prompt(DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert "You may never change facts" in prompt and "coarse salt (not: kosher salt" in prompt
    assert "- Salads & Sides" in prompt
    assert "<source_text>" in user_text(MATERIAL)
    assert "embedded" in user_text(SourceMaterial(kind="url", text="x", has_recipe_data=True))
    assert "attached images" in user_text(SourceMaterial(kind="photo", images=["a.jpg"]))


def test_local_structurer_builds_recipes():
    structurer, calls = ollama(lambda n: chat_reply(REPLY))
    [recipe] = structurer.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert recipe.title == "Brown-Butter Shortbread" and recipe.structured_by == "local"
    assert [i.text for i in recipe.ingredients()] == ["1 cup unsalted butter", "2¼ cups all-purpose flour"]
    assert recipe.steps[1].lead == "Bake" and recipe.total_minutes == 90
    assert recipe.source.credit() == "Source: Sample Cookbook, page 112"  # page read off the photo
    assert recipe.original_text == MATERIAL.text and recipe.original_files == ["/o/a.heic"]
    assert [f.kind for f in recipe.flags] == ["headnote_generated"]
    sent = calls[0]
    assert sent["format"] == output_schema(DEFAULT_CATEGORIES) and sent["stream"] is False
    assert sent["options"]["temperature"] == 0 and sent["messages"][0]["role"] == "system"


def test_local_structurer_retries_once_on_a_broken_reply():
    structurer, calls = ollama(lambda n: chat_reply('{"recipes": [{"title": "cut off') if n == 1 else chat_reply(REPLY))
    assert len(structurer.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)) == 1 and len(calls) == 2
    structurer, calls = ollama(lambda n: chat_reply("not json"))
    with pytest.raises(StructurerError, match="cut off or malformed") as error:
        structurer.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert len(calls) == 2 and "Retry with Claude" in error.value.advice


def test_local_structurer_waits_when_ollama_is_down_or_model_missing():
    def refuse(request):
        raise httpx.ConnectError("refused")

    down = LocalStructurer(client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(StructurerUnavailable, match="not running") as error:
        down.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert "ollama serve" in error.value.fix
    missing, _ = ollama(lambda n: chat_reply(REPLY), models=("llama3:latest",))
    with pytest.raises(StructurerUnavailable, match="not installed") as error:
        missing.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert "ollama pull qwen2.5:7b" in error.value.fix


def test_local_structurer_cannot_read_images():
    structurer, calls = ollama(lambda n: chat_reply(REPLY))
    with pytest.raises(StructurerError, match="cannot read images"):
        structurer.structure(SourceMaterial(kind="photo", images=["a.jpg"]), DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert calls == []


def test_no_recipe_found_and_unknown_category():
    structurer, _ = ollama(lambda n: chat_reply('{"recipes": []}'))
    assert structurer.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY) == []
    odd = json.dumps({"recipes": [{**DRAFT, "category": "Snacks"}]})
    structurer, _ = ollama(lambda n: chat_reply(odd))
    [recipe] = structurer.structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert recipe.category == DEFAULT_CATEGORIES[0] and "category_unclear" in [f.kind for f in recipe.flags]


class FakeClaude:
    def __init__(self, reply=None, stop_reason="end_turn", error=None):
        self.calls, self._reply, self._stop, self._error = [], reply, stop_reason, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(stop_reason=self._stop, content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self._reply)])


def test_claude_structurer_sends_images_schema_and_fallbacks(tmp_path):
    photo = tmp_path / "page.jpg"
    Image.new("RGB", (40, 30), "white").save(photo)
    material = MATERIAL.model_copy(update={"images": [str(photo)]})
    client = FakeClaude(REPLY)
    [recipe] = ClaudeStructurer(client=client).structure(material, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert recipe.structured_by == "claude" and recipe.title == "Brown-Butter Shortbread"
    call = client.calls[0]
    assert call["model"] == CLAUDE_MODEL == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": output_schema(DEFAULT_CATEGORIES)}
    assert "thinking" not in call and "temperature" not in call
    image, text = call["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg" and "\n" not in image["source"]["data"]
    assert text["type"] == "text" and "trust the image" in text["text"]


def _status_error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize("kwargs, phrase", [
    (dict(reply=REPLY, stop_reason="refusal"), "declined"),
    (dict(reply='{"recipes": [', stop_reason="max_tokens"), "too long"),
    (dict(reply="not json"), "could not be read"),
])
def test_claude_stop_reasons(kwargs, phrase):
    with pytest.raises(StructurerError, match=phrase):
        ClaudeStructurer(client=FakeClaude(**kwargs)).structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)


def test_claude_errors_become_plain_reasons():
    cases = [
        (_status_error(anthropic.AuthenticationError, 401), "did not accept the API key"),
        (_status_error(anthropic.RateLimitError, 429), "rate-limiting"),
        (_status_error(anthropic.InternalServerError, 500), r"returned an error \(500\)"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")), "could not be reached"),
    ]
    for error, phrase in cases:
        with pytest.raises(StructurerError, match=phrase):
            ClaudeStructurer(client=FakeClaude(error=error)).structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)


def test_claude_needs_a_key():
    with pytest.raises(StructurerError, match="No Claude API key") as error:
        ClaudeStructurer(api_key=None).structure(MATERIAL, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
    assert "Settings" in error.value.advice
