"""Structurers turn SourceMaterial into draft recipes in house style.

Two interchangeable implementations share one prompt and one output schema:
a local model through Ollama, and Claude.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..model import Ingredient, IngredientGroup, Flag, Recipe, Step
from ..style.glossary import GlossaryEntry
from .material import SourceMaterial

STYLE_GUIDE = (Path(__file__).parent.parent / "style" / "style_guide.md").read_text(encoding="utf-8")
CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434"
USE_CLAUDE = "Use Retry with Claude on this item."


class StructurerError(Exception):
    """Structuring failed for this item. `advice` says what the user can do."""

    def __init__(self, message: str, advice: str = ""):
        super().__init__(message)
        self.advice = advice


class StructurerUnavailable(Exception):
    """The structurer cannot run right now (for example Ollama is not started). The job should wait."""

    def __init__(self, message: str, fix: str = ""):
        super().__init__(message)
        self.fix = fix


# ---------------------------------------------------------------- shared schema

class DraftGroup(BaseModel):
    name: str | None = None
    items: list[str] = Field(default_factory=list)


class DraftStep(BaseModel):
    lead: str | None = None
    text: str


class DraftRecipe(BaseModel):
    title: str
    headnote: str = ""
    headnote_from_source: bool = True
    yield_label: Literal["Serves", "Makes"] = "Serves"
    yield_value: str = ""
    active_minutes: int | None = None
    total_minutes: int | None = None
    ingredient_groups: list[DraftGroup] = Field(default_factory=list)
    steps: list[DraftStep] = Field(default_factory=list)
    note: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    page_number: str | None = None


class DraftBatch(BaseModel):
    recipes: list[DraftRecipe] = Field(default_factory=list)


def output_schema(categories: list[str]) -> dict:
    """The JSON schema both models must answer in. Every field is required; no extras."""

    def obj(properties: dict) -> dict:
        return {"type": "object", "properties": properties, "required": list(properties),
                "additionalProperties": False}

    text, maybe_text = {"type": "string"}, {"type": ["string", "null"]}
    recipe = obj({
        "title": text,
        "headnote": text,
        "headnote_from_source": {"type": "boolean"},
        "yield_label": {"type": "string", "enum": ["Serves", "Makes"]},
        "yield_value": text,
        "active_minutes": {"type": ["integer", "null"]},
        "total_minutes": {"type": ["integer", "null"]},
        "ingredient_groups": {"type": "array", "items": obj({"name": maybe_text, "items": {"type": "array", "items": text}})},
        "steps": {"type": "array", "items": obj({"lead": maybe_text, "text": text})},
        "note": text,
        "category": {"type": "string", "enum": list(categories)},
        "tags": {"type": "array", "items": text},
        "page_number": maybe_text,
    })
    return obj({"recipes": {"type": "array", "items": recipe}})


def system_prompt(categories: list[str], glossary: tuple[GlossaryEntry, ...]) -> str:
    names = "\n".join(
        f"- {entry.preferred} (not: {', '.join(entry.variants)})" for entry in glossary if entry.variants)
    return (
        "You turn recipes from web pages, PDFs, and cookbook photos into one house format.\n\n"
        f"{STYLE_GUIDE}\n"
        f"## Categories\n\n{chr(10).join('- ' + c for c in categories)}\n\n"
        f"## Glossary of preferred ingredient names\n\n{names}\n\n"
        "## Output\n\n"
        "Return every complete recipe you find, one entry each. A page with two recipes gives two entries. "
        "If the material holds no recipe, return an empty list. Set `page_number` to the printed page number "
        "when one is visible, otherwise null. Ignore navigation, ads, comments, and nutrition tables."
    )


def user_text(material: SourceMaterial) -> str:
    where = {"url": "a web page", "pdf": "a PDF", "photo": "a cookbook photo"}[material.kind]
    if material.has_recipe_data:
        lead = f"This recipe comes from recipe data embedded in {where}. Rewrite it into house style."
    elif material.text.strip():
        lead = f"This text was read from {where}. Find the recipe or recipes in it and rewrite them into house style."
    else:
        lead = f"Find the recipe or recipes in the attached images of {where} and rewrite them into house style."
    if material.images and material.text.strip():
        lead += " The page images are attached; where the text and an image disagree, trust the image."
    body = f"\n\n<source_text>\n{material.text.strip()}\n</source_text>" if material.text.strip() else ""
    return lead + body


def to_recipes(batch: DraftBatch, material: SourceMaterial, structured_by: str, categories: list[str]) -> list[Recipe]:
    """Turn model drafts into Recipe objects, carrying the source and the original along."""
    recipes = []
    for draft in batch.recipes:
        groups = [IngredientGroup(name=g.name, items=[Ingredient(text=line) for line in g.items if line.strip()])
                  for g in draft.ingredient_groups]
        flags = []
        if draft.headnote and not draft.headnote_from_source:
            flags.append(Flag(kind="headnote_generated", severity="info", field="headnote",
                              message="The headnote was written by the AI; the source had no introduction."))
        if draft.category not in categories:
            flags.append(Flag(kind="category_unclear", severity="warning", field="category",
                              message="The AI did not pick one of your categories. Please choose one."))
        source = material.source
        if draft.page_number and source.kind == "cookbook" and not source.page:
            source = source.model_copy(update={"page": draft.page_number.strip()})
        recipes.append(Recipe(
            title=draft.title.strip(), headnote=draft.headnote.strip(),
            yield_label=draft.yield_label, yield_value=draft.yield_value.strip(),
            active_minutes=draft.active_minutes, total_minutes=draft.total_minutes,
            ingredient_groups=[g for g in groups if g.items],
            steps=[Step(lead=s.lead, text=s.text) for s in draft.steps if s.text.strip()],
            note=draft.note.strip(),
            category=draft.category if draft.category in categories else categories[0],
            tags=draft.tags[:6], source=source,
            original_text=material.text, original_files=material.files + material.images,
            structured_by=structured_by, flags=flags,
        ))
    return recipes


def _parse(raw: str) -> DraftBatch:
    return DraftBatch.model_validate(json.loads(raw))


# ---------------------------------------------------------------- local (Ollama)

class LocalStructurer:
    name = "local"

    def __init__(self, model: str = DEFAULT_LOCAL_MODEL, base_url: str = OLLAMA_URL, client: httpx.Client | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(600.0, connect=3.0))

    def check(self) -> None:
        """Raise StructurerUnavailable unless Ollama is running and has the model."""
        try:
            response = self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            response.raise_for_status()
        except httpx.HTTPError:
            raise StructurerUnavailable("Ollama is not running.", "Open the Ollama app, or run:  ollama serve") from None
        installed = {m.get("name", "") for m in response.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in installed and self.model not in installed:
            raise StructurerUnavailable(f"The local model “{self.model}” is not installed.",
                                        f"Run:  ollama pull {self.model}")

    def structure(self, material: SourceMaterial, categories: list[str], glossary) -> list[Recipe]:
        if not material.text.strip():
            raise StructurerError("No text could be read from this item, and the local model cannot read images.",
                                  USE_CLAUDE)
        self.check()
        payload = {
            "model": self.model, "stream": False, "format": output_schema(categories),
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system_prompt(categories, glossary)},
                         {"role": "user", "content": user_text(material)}],
        }
        last_error = ""
        for _attempt in range(2):  # one automatic retry when the reply does not parse
            try:
                response = self._client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
            except httpx.ConnectError:
                raise StructurerUnavailable("Ollama stopped answering.", "Open the Ollama app, or run:  ollama serve") from None
            except httpx.HTTPError as error:
                raise StructurerError(f"The local model failed ({type(error).__name__}).", USE_CLAUDE) from None
            try:
                batch = _parse(response.json().get("message", {}).get("content", ""))
            except (json.JSONDecodeError, ValidationError, AttributeError) as error:
                last_error = type(error).__name__
                continue
            return to_recipes(batch, material, "local", categories)
        raise StructurerError(f"The local model's reply was cut off or malformed ({last_error}).", USE_CLAUDE)


# ---------------------------------------------------------------- Claude

class ClaudeStructurer:
    name = "claude"

    def __init__(self, api_key: str | None = None, client=None):
        self._api_key = api_key
        self._client = client

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise StructurerError("No Claude API key has been saved.", "Add your key on the Settings page.")
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def structure(self, material: SourceMaterial, categories: list[str], glossary) -> list[Recipe]:
        import anthropic

        client = self._get_client()
        content: list[dict] = []
        for image in material.images:
            data = base64.standard_b64encode(Path(image).read_bytes()).decode("ascii")
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        content.append({"type": "text", "text": user_text(material)})
        if not material.images and not material.text.strip():
            raise StructurerError("There is nothing to read in this item.")

        try:
            response = client.beta.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # on a safety decline, the request is re-run on a fallback model
                system=system_prompt(categories, glossary),
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": output_schema(categories)}},
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AuthenticationError:
            raise StructurerError("Claude did not accept the API key.", "Check the key on the Settings page.") from None
        except anthropic.RateLimitError:
            raise StructurerError("Claude is rate-limiting this key right now.", "Wait a minute, then retry.") from None
        except anthropic.APIStatusError as error:
            raise StructurerError(f"Claude returned an error ({error.status_code}).", "Retry in a moment.") from None
        except anthropic.APIConnectionError:
            raise StructurerError("Claude could not be reached.", "Check your internet connection, then retry.") from None

        if response.stop_reason == "refusal":
            raise StructurerError("Claude declined to process this item.", "Enter this recipe by hand with New recipe.")
        if response.stop_reason == "max_tokens":
            raise StructurerError("The recipe was too long for one reply.", "Split the input into fewer pages and add it again.")
        raw = next((block.text for block in response.content if block.type == "text"), "")
        try:
            batch = _parse(raw)
        except (json.JSONDecodeError, ValidationError):
            raise StructurerError("Claude's reply could not be read.", "Retry in a moment.") from None
        return to_recipes(batch, material, "claude", categories)
