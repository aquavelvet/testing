# Recipe Book: Implementation Plan

- **Date:** 2026-11-26
- **Spec:** `docs/superpowers/specs/2026-11-26-recipe-book-design.md`
- **Approach:** four milestones, each usable on its own. Every unit ships with its tests. Milestone 1 is planned in task detail; later milestones are planned at the unit level and get detailed when they start.

## Project layout

```
pyproject.toml
src/recipebook/
  config.py            data folder paths (RECIPEBOOK_HOME overrides ~/RecipeBook)
  model.py             Recipe, Ingredient, IngredientGroup, Step, Source, Flag
  style/
    numbers.py         parse and format quantities and fractions
    units.py           unit table and normalizer
    parser.py          ingredient-line parser
    glossary.py        default glossary and its application
    fidelity.py        number comparison between original and draft
    housestyle.py      one entry point that applies all code rules to a recipe
    style_guide.md     rules given to the structurers (milestone 2)
  library.py           SQLite schema, recipe CRUD, settings, glossary
  render/
    fonts/             bundled TTF files and their licenses
    templates/         recipe.css, recipe.html.j2
    pdf.py             layout selection (auto-fit) and PDF output
  web/
    app.py             FastAPI app and routes
    forms.py           form text <-> Recipe
    templates/, static/
  cli.py               `recipebook`, `recipebook doctor`
tests/
```

## Milestone 1: Core and print

Goal: type a recipe into a form, have the code rules put it into house style, save it to the library, and get a correct A5 PDF.

1. **Skeleton.** `pyproject.toml` for `uv` (Python 3.12+), package layout, pytest setup.
2. **Model.** Pydantic types per spec section 4. Quantities are exact fractions. `structured_by` also allows "manual" for recipes typed in by hand.
3. **Numbers.** Parse "1", "1/2", "1 1/2", "1½", "0.5", and ranges ("3 to 4", "3-4"). Format back to fraction characters.
4. **Units.** Table of canonical units with plurals and abbreviations. Normalizer spells units out and fixes plurals.
5. **Ingredient-line parser.** House-style line to quantity, unit, item, prep, optional. Handles parentheticals ("(1 stick)"), "plus more", "for serving", and commas inside the item ("firm, tart apples").
6. **Glossary.** About 30 default entries; applied to lines without double-applying ("pure vanilla extract" stays as is).
7. **Fidelity check.** Flags per spec section 5.2.
8. **House style entry point.** Applies normalizer, fractions, glossary, and parser to a whole recipe.
9. **Library.** SQLite schema with `AUTOINCREMENT` recipe numbers (never reused), recipe CRUD, the five categories, glossary table.
10. **Renderer.** Fonts bundled as full TTF files with licenses. Templates ported from the approved mockup. Auto-fit per spec section 9.3. Binding margins per section 9.5.
11. **Web app.** Library page, recipe form (ingredients and directions as plain text boxes: one ingredient per line, a line ending in a colon starts a group; one step per paragraph, a short phrase before a colon becomes the bold lead-in), preview PDF, export PDF, delete.
12. **CLI.** `recipebook` starts the server and opens the browser. `recipebook doctor` checks WeasyPrint, fonts, and the data folder.

**Tests:** numbers, units, parser, glossary, fidelity, library (including number reuse), form parsing, renderer (layout choice and page count for four recipe lengths, no text past the text area, fraction glyphs present), and a web smoke test (create a recipe, fetch its PDF).

**Done when:** the full test suite passes, and a recipe entered through the form in a real browser produces a PDF that matches the mockup.

Deferred from milestone 1 on purpose: notes lines and QR codes (milestone 3), search (milestone 4), anything that calls a model (milestone 2).

## Milestone 2: Intake

- `readers`: URL (embedded recipe data, then page text), PDF (text layer, then OCR), photo (HEIC, rotation, Apple Vision OCR). Each returns `SourceMaterial`.
- `structurers`: shared interface and schema; local (Ollama, JSON schema output) and Claude (`claude-opus-5-5`, structured outputs, image and PDF input, refusal fallback). `style_guide.md` and glossary in the prompt.
- `pipeline`: jobs table, single background worker, restart recovery.
- Web: Add, Queue, Review (original beside the form, flags on fields, Retry with Claude), Settings (model, default structurer, Claude key in the Keychain).
- `recipebook doctor` gains OCR, Ollama, and Claude checks.
- Evaluation set script for choosing the local model (run on the Mac).

Mac-only pieces (Apple Vision, Ollama) sit behind interfaces and are tested with fakes here, then verified on the Mac.

## Milestone 3: Book

- Layout cache per recipe.
- Notes lines and QR code, placed from measured free space.
- Book assembly: cover, contents, dividers on right-hand pages, recipe ordering that avoids blank pages, index.
- Editions table with the page map.
- Export screen: title, subtitle, categories or tag, binding, switches.
- Tests: contents and index numbers match real pages; spreads start on left-hand pages.

## Milestone 4: Find and combine

- FTS5 search index and the Library search box.
- Ingredient list: page and recipe-number entry, edition lookup, merge rules per spec section 8.3, copy as text.
- Cookbook batch mode, inbox folder watcher, duplicate warning.
- End-to-end test across the whole flow.

## Working agreements

- Work happens on a branch per milestone; `main` only moves when the user asks.
- No live model calls in the automated tests.
- The mockup folder stays as the visual reference; real templates live in `src/recipebook/render/templates/`.
