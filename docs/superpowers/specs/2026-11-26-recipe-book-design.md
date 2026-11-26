# Recipe Book: Design Spec

- **Date:** 2026-11-26
- **Status:** Awaiting review
- **Visual reference:** `docs/design/a5-template-mockup/A5-template-set.pdf` (approved mockup; the CSS and template beside it are the starting point for the real templates)

## 1. Purpose

A local app for one person on an Apple Silicon Mac. It takes recipes from web URLs, PDFs, and photos of cookbook pages, rewrites each one into a single house format modeled on Martha Stewart's recipe conventions, and produces print-ready A5 PDFs: one per recipe, and a full recipe book with cover, contents, sections, and index.

It runs offline wherever possible. The only network use is fetching URLs the user adds and, when the user asks for it, calling Claude.

## 2. Decisions

| Topic | Decision |
|---|---|
| Inputs | URLs, PDFs (text or scanned), photos (JPEG, PNG, HEIC) |
| Output | A5 PDF per recipe, plus a full book PDF |
| Interface | Local web page served on 127.0.0.1 |
| Platform | macOS on Apple Silicon |
| Extraction | Local model (Ollama) by default; "Retry with Claude" per recipe |
| Review | Every recipe is reviewed and edited by the user before it is saved |
| House style | Martha Stewart conventions for structure, wording, and look. Style only, no branding |
| Wording | The AI rewrites wording to house style; amounts may never change |
| Fields | Title, headnote, yield, active time, total time, ingredients (grouped), directions, cook's note, category, tags, source credit. No dish photos |
| Categories | Five, by course (section 4.4). Seasons and occasions are tags |
| Recipe number | Permanent number per recipe, printed on the page |
| Search | Local full-text search by title, ingredient, tag, source, or number |
| Ingredient list | Enter page numbers or recipe numbers, get one merged list |

## 3. Architecture

### 3.1 Stack

- **Python 3.12+**, managed with `uv`. Package name `recipebook`.
- **FastAPI + Uvicorn** for the local server. Binds to 127.0.0.1 only.
- **Jinja2 templates + htmx** for the interface. No frontend build step.
- **SQLite** (standard library `sqlite3`, with FTS5) for the library and search index.
- **Pydantic v2** for the shared data model.
- **WeasyPrint** for PDF output. Needs Pango on the Mac (`brew install pango`).
- **pypdfium2** for reading PDFs and rendering scanned pages to images.
- **ocrmac** (Apple Vision framework) for offline text recognition. macOS only.
- **pillow + pillow-heif** for image loading, HEIC conversion, and EXIF rotation.
- **Ollama** (installed separately) for the local model, called over its local HTTP API.
- **anthropic** Python SDK for Claude.
- **keyring** to keep the Claude API key in the macOS Keychain.
- **segno** for QR codes.

### 3.2 How it runs

`uv run recipebook` starts the server and opens the browser. `uv run recipebook doctor` checks the machine: Pango, bundled fonts, Apple Vision OCR, Ollama and its model, and the Claude key.

### 3.3 Data folder

Everything lives in `~/RecipeBook/`:

```
~/RecipeBook/
  library.db      recipes, jobs, settings, glossary, editions, search index
  originals/      a copy of every source file and web page snapshot
  inbox/          watched folder; files dropped here are queued automatically
  exports/        generated PDFs
```

Backing up this one folder backs up everything.

### 3.4 Units

Each unit has one job and talks to the others only through the shared `Recipe` model.

| Unit | Job | Depends on |
|---|---|---|
| `model` | Pydantic types for Recipe, Ingredient, Source, Job | nothing |
| `readers` | Turn an input into `SourceMaterial` (text, images, any structured data found) | pypdfium2, ocrmac, httpx |
| `structurers` | Turn `SourceMaterial` into draft recipes in house style | Ollama or Claude |
| `style` | Code-only rules: unit and fraction normalizer, ingredient-line parser, glossary, fidelity check | `model` |
| `library` | Store, load, edit, search recipes; jobs; editions | SQLite |
| `pipeline` | Background worker that runs jobs through readers, structurer, style | all of the above |
| `render` | Recipe or library to PDF; layout selection; book assembly | WeasyPrint |
| `shopping` | Resolve page or recipe numbers; merge ingredient lists | `library`, `style` |
| `web` | Routes and pages | everything |

## 4. Recipe data model

### 4.1 Recipe

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Permanent recipe number. Assigned when a draft is first saved to the library. Never reused, never changes. Printed as "No. 142" |
| `title` | text | |
| `headnote` | text or empty | One or two sentences (section 5.3) |
| `yield_label` | "Serves" or "Makes" | |
| `yield_value` | text | "8", "24", "About 2 cups" |
| `active_minutes` | integer or empty | Printed as "25 minutes", "1 hour 45 minutes" |
| `total_minutes` | integer or empty | |
| `ingredient_groups` | list of groups | Each group: optional name ("For the topping") and a list of ingredients |
| `steps` | list | Each step: optional lead-in ("Make the topping") and text |
| `note` | text or empty | Cook's note |
| `category` | one of the five | Decides the book section |
| `tags` | list of text | Season, occasion, anything else |
| `source` | Source | Section 4.3 |
| `original_text` | text | Raw text the draft was made from, for side-by-side review and the fidelity check |
| `original_files` | list of paths | Files in `originals/` |
| `structured_by` | "local" or "claude" | |
| `flags` | list | Review warnings (section 10) |
| `created_at`, `updated_at` | timestamps | |

To be saved, a recipe needs a title, at least one ingredient, at least one step, and a category. Everything else may be empty.

### 4.2 Ingredient

Each ingredient is stored two ways: the printed line, and its parts.

| Field | Example |
|---|---|
| `text` | "8 tablespoons (1 stick) unsalted butter, melted" (this is what prints) |
| `quantity` | 8 |
| `quantity_max` | empty, or the upper end of a range ("3 to 4 tablespoons" stores 3 and 4) |
| `unit` | "tablespoon" (canonical singular), or empty |
| `item` | "unsalted butter" (canonical name after the glossary) |
| `prep` | "melted" |
| `optional` | true for "for serving", "for garnish", "optional" |

The printed line is the source of truth for the page. The parts exist for search and for merged ingredient lists. When the user edits a line on the review screen, the code parser (section 5.2) re-derives the parts. A line the parser cannot read keeps its text, has empty parts, and appears unmerged in ingredient lists.

### 4.3 Source

`kind` is "web", "cookbook", or "other". Web sources store the URL. Cookbook sources store title, author, and page. "Other" stores a free-text label ("Handwritten family recipe card"). The printed credit is built from these: "Source: example.com/maple-whipped-cream" or "Source: Sample Cookbook, by A. N. Author, page 112".

### 4.4 Categories

Five by default, in this order. Names and order are editable in Settings; the count stays at five in version 1.

1. Breakfast & Brunch
2. Starters & Soups (appetizers, snacks, soups, drinks)
3. Main Dishes
4. Salads & Sides
5. Desserts & Baking (sweets and breads)

The structurer suggests a category and tags; the user confirms on review.

## 5. House style

### 5.1 Style guide

One file, `style_guide.md`, ships with the app and is given to both structurers. Rules:

- **Ingredient lines:** quantity, unit, ingredient, then preparation after a comma. "2 tablespoons unsalted butter, softened."
- **Units** are spelled out: tablespoon, teaspoon, cup, ounce, pound. Never "tbsp" or "c."
- **Fractions** print as real fraction characters: ½, ¼, ¾, ⅓, ⅔, ⅛.
- **Ingredient order** follows order of use.
- **Groups** ("For the crust") are used only when the source has distinct components.
- **Directions** are one continuous numbered list in plain imperative sentences. Where a new component starts, the step opens with a bold lead-in: "**Make the topping:** In a medium bowl...".
- **Oven temperature** is stated at the step where the oven is first needed, written "Preheat oven to 375 degrees." That is step 1 unless the recipe chills or rests something first.
- **Ranges** use "to": "50 to 60 minutes."
- **No unit conversion.** Metric stays metric; US stays US.

### 5.2 Rules enforced by code

These run after the structurer, on every draft, so results are consistent even when the local model slips:

- **Unit normalizer:** expands abbreviations, fixes plurals.
- **Fraction formatter:** "1/2" and "0.5" become "½"; "1 1/2" becomes "1½".
- **Glossary:** an editable table of preferred ingredient names and their variants (for example "coarse salt" for "kosher salt", "confectioners' sugar" for "powdered sugar"). Seeded with about 30 entries in Martha Stewart usage. Applied to the `item` and the printed line. The glossary is also included in the structurer prompt.
- **Ingredient-line parser:** reads a house-style line into quantity, unit, item, prep, and optional. Pure code, no AI.
- **Fidelity check:** compares numbers between the original and the draft. Numbers are normalized first ("1/2", "½", and "0.5" are equal). Two kinds of flag:
  - *Changed or added amount:* a number in a draft ingredient line or step that does not appear in the original. Shown on that line in red.
  - *Possibly dropped:* a number in the original that does not appear in the draft. Lower severity, because raw text carries noise such as page numbers.

  For web recipes with embedded recipe data, the comparison uses that data, which is clean.

### 5.3 Headnote

If the source has an intro or description, the headnote condenses it to one or two sentences. If it has none, the AI writes one plain sentence using only facts in the recipe ("A one-bowl shortbread flavored with browned butter"), and the draft is flagged "headnote written by AI" so the user sees it on review. The headnote never adds claims the source does not support.

## 6. Pipeline

### 6.1 Jobs

Every input becomes a job, saved in the database. States: `queued`, `reading`, `structuring`, `needs_review`, then `saved`, `failed`, or `discarded`. One background worker processes jobs one at a time. On startup, jobs left in `reading` or `structuring` go back to `queued`.

### 6.2 Readers

All readers return `SourceMaterial`: text, page images, any structured recipe data found, and a source guess.

- **URL reader.** Fetches the page (20 second timeout) and saves a snapshot to `originals/`. If the page embeds schema.org Recipe data, uses it. Otherwise extracts the readable text of the page.
- **PDF reader.** If the PDF has a text layer, uses it. If it is a scan, renders each page at 300 dpi and runs OCR. One intake covers up to 10 pages; for a longer PDF, the Add screen asks for a page range.
- **Photo reader.** Converts HEIC, fixes rotation, runs Apple Vision OCR. Several photos marked "one recipe" are read in order and joined.

### 6.3 Structurers

Both implement one interface: `structure(material, style_guide, glossary) -> list of draft recipes`. A page with two recipes returns two drafts. Both return the same schema, including each ingredient's printed line and parts, a suggested category and tags, and any page number seen on the page.

- **Local.** Calls Ollama on localhost with a JSON schema so the reply always parses. Works from the reader's text. The model is a setting; the default is chosen during the build by scoring candidates in the 8B class on the evaluation set (section 11.4).
- **Claude.** Uses the `anthropic` SDK with model `claude-opus-5-5` and structured outputs, so the reply always matches the schema. Sends the original photo or PDF pages directly along with the reader's text, because Claude reads images better than OCR text. Server-side refusal fallback is enabled. The reply's stop reason is checked before use. Exact SDK calls are taken from current Anthropic documentation at build time.

Claude is called only when the user clicks **Retry with Claude**, or when they set Claude as the default structurer in Settings.

### 6.4 After structuring

In order: unit normalizer, fraction formatter, glossary, ingredient-line parser, fidelity check, duplicate check. The draft then waits in `needs_review`.

### 6.5 Intake helpers

- **Cookbook batch mode.** On the Add screen, optional cookbook title and author apply to every item in the batch. The page number comes from the page itself when the structurer can see it, and is editable.
- **Inbox folder.** `~/RecipeBook/inbox/` is checked every 5 seconds. A file is picked up once its size stops changing, moved to `originals/`, and queued. Accepts JPEG, PNG, HEIC, and PDF.
- **Duplicate warning.** A draft is flagged when it has the same URL as a saved recipe, or a title at least 90% similar together with an ingredient set that overlaps by at least 80%. The warning links to the existing recipe. The user may still save.

## 7. Screens

- **Add.** Paste URLs or drag in photos and PDFs. Options: "these photos are one recipe", and the cookbook batch fields.
- **Queue.** Every job with its state, and for failures the reason and the fix.
- **Review.** Original on the left (photo, PDF page, or text). Editable recipe on the right, with flags shown on the fields they concern. Buttons: Preview PDF, Retry with Claude, Save to library, Discard.
- **Library.** Recipes by category, with a search box that filters as you type. Open a recipe to edit it or export its PDF.
- **Ingredient list.** Section 8.
- **Export book.** Title, subtitle, which categories or which tag, binding, and the notes-line and QR switches.
- **Settings.** Category names and order, glossary, local model name, default structurer, Claude API key.

## 8. Search and ingredient lists

### 8.1 Search

An FTS5 index covers title, headnote, ingredient lines and items, directions, note, tags, and source. Typing a number, "#142", or "No. 142" finds that recipe directly.

### 8.2 Editions and page numbers

Every book export is saved as an **edition**: date, title, filters, and a page map from each page to its recipe. Page numbers change whenever the book is exported again; recipe numbers never do.

### 8.3 Ingredient list

The screen has two input modes:

- **Pages** (default). Enter pages and ranges: "34, 36-37". They are resolved against an edition, the latest by default. Either page of a spread selects that recipe. Pages that are not recipes are skipped with a note.
- **Recipe numbers.** Enter "118, 142, 157".

The app shows the matched recipe titles, then one merged list:

- Lines are grouped by ingredient `item`.
- Amounts with the same unit are added. Different units for the same item are shown side by side and not converted: "all-purpose flour: 3¾ cups + 2 tablespoons".
- Ranges add their low and high ends separately.
- Each line names the recipes that use it: "(Nos. 118, 142)".
- Items with no amount ("Pinch of coarse salt") are listed once.
- Optional and "for serving" items go in their own section at the end.
- Lines the parser could not read are listed as written, under their recipe.

The list can be copied as plain text.

## 9. PDF output

### 9.1 Page design

A5 (148 x 210 mm). Fonts, all open-licensed and bundled with the app as full font files: Cormorant Garamond for titles and headnotes, Source Serif 4 for body text, Jost for small labels. Colors: text `#2b2b2b`, accent `#4b7264`, tint `#edf3f0`, rules `#c9d6d0`. The mockup PDF is the reference for every template.

### 9.2 Templates

| Template | Content |
|---|---|
| Cover | Title, subtitle, edition line, inside a thin frame |
| Contents | Categories and recipes with dotted leaders and real page numbers |
| Section divider | Tinted page with the category name and its recipes |
| Recipe, one page | Category and recipe number, title, headnote, yield and times, ingredients beside directions, cook's note |
| Recipe, spread | Left page: heading block and ingredients in two columns. Right page: directions and cook's note |
| Index | Alphabetical by title, two columns, letter headings |

The footer of recipe pages has the page number on the outer edge and the source credit on the inner edge.

### 9.3 Choosing a layout (auto-fit)

For each recipe:

1. Render the one-page template with 8.5 pt body text. If it fits on one page, done.
2. Otherwise try 8.3, 8.1, then 8.0 pt. The first that fits is used. 8.0 pt is the floor.
3. Otherwise render the spread template with 9 pt body text. It must come out as exactly two pages. If the ingredients page overflows, retry at 8.5 pt.
4. If it still does not fit, use the spread template and let the directions run onto further pages. The recipe is listed in the export report.

The result (layout, size, page count) is cached per recipe and reused until the recipe changes. All binding settings share the same text width, so the cache does not depend on binding.

### 9.4 Notes lines and QR code

Both are switches on the Export screen and apply to one-page recipes.

- **Notes lines** (on by default): when at least 25 mm is free at the bottom of the page, ruled lines 7.2 mm apart fill it under a "Notes" label.
- **QR code** (on by default): for web sources only, and only when at least 22 mm is free. It links to the source URL and sits at the bottom right beside the notes lines. When there is no room it is left out; the footer still credits the source in text.

### 9.5 Binding

| Setting | Inner margin | Outer margin |
|---|---|---|
| None | 14 mm | 14 mm |
| Bound book | 17 mm | 11 mm |
| Ring binder | 19 mm | 9 mm |

Top margin is 12 mm and bottom is 16 mm in all cases. Text width is always 120 mm.

### 9.6 Book assembly

1. Cover on page 1; contents from page 2.
2. For each category that has recipes: a divider on a right-hand page, then its recipes.
3. Recipes within a category are alphabetical by title. A spread must start on a left-hand page. If a spread would start on a right-hand page, the next one-page recipe is moved ahead of it. If there is none, a ruled "Notes" page fills the gap.
4. Index at the end.

The book can include everything, chosen categories, or one tag (for example a "Thanksgiving" booklet, still ordered by course). The file is written to `exports/` and the edition is recorded.

A single-recipe export uses the same templates with the "None" binding and no page number.

## 10. Error handling

| Situation | What the app does |
|---|---|
| URL cannot be fetched (timeout, blocked, paywall) | Job fails with the reason and a suggestion: save the page as a PDF or screenshot and add that |
| No recipe found in the material | Job fails as "No recipe found". The original is kept. Retry with Claude is offered |
| OCR finds fewer than 200 characters | Draft is flagged "photo may be blurry", with Retry with Claude offered |
| Ollama is not running, or the model is missing | Banner on the Queue with the exact fix. Jobs stay queued and resume on their own once it is available |
| Local model reply is cut off or invalid | One automatic retry, then the job fails with Retry with Claude offered |
| Claude key is missing | Prompt to add it in Settings |
| Claude call fails (bad key, rate limit, refusal, offline) | Job fails with a plain-language reason. Rate limits are retried automatically first |
| Fidelity flags, missing yield or times, unclear category | Draft is still created; the fields are flagged on Review |
| Probable duplicate | Warning on Review with a link to the existing recipe |
| Recipe does not fit a spread | Falls back to a flowing layout and is listed in the export report |
| App quits mid-job | Unfinished jobs are re-queued at next start |

Other rules:

- Original files are never deleted automatically. Discarding a draft asks whether to delete its original; the default is to keep it.
- Database writes happen in transactions.
- Outbound connections are limited to: URLs the user adds, Ollama on localhost, and the Claude API when the user chooses it.

## 11. Testing

### 11.1 Unit tests (pytest)

Unit and fraction normalizer; ingredient-line parser; fidelity check; glossary; ingredient merging; duplicate detection; page-entry parsing ("34, 36-37"); the URL reader against saved HTML pages; the PDF reader against sample PDFs.

### 11.2 Structurers

Tested with fake and recorded responses for schema handling, retries, and error paths. The test suite makes no live model calls.

### 11.3 Rendering

Sample recipes of four lengths (short, medium, long, very long) are rendered and checked:

- The expected layout and page count are chosen.
- No text box extends past the text area. This guards against the 9 mm column overrun found in the mockup.
- Every fraction character used by the formatter exists in the bundled body font.
- In a book export: contents and index page numbers match the real pages, spreads start on left-hand pages, and dividers fall on right-hand pages.

### 11.4 Evaluation set (run on the Mac, not automated)

About ten of the user's own recipes (3 URLs, 3 PDFs, 4 photos) with hand-checked expected results. Used to choose the default local model and to measure field accuracy and fidelity flags for local versus Claude.

### 11.5 End to end

One automated test with a fake reader and fake structurer: add, queue, review, save, search, ingredient list, export.

### 11.6 Mac-only parts

Apple Vision OCR and Ollama cannot run in a Linux build environment. They sit behind interfaces and are exercised with fakes in automated tests, then verified on the Mac with `recipebook doctor` and the evaluation set.

## 12. Out of scope for version 1

Dish photos; unit conversion; recipe scaling; nutrition facts; meal planning; accounts or sync; a phone interface; an ingredient index in the book; "tested" versus "to try" status; printing original handwritten cards; page sizes other than A5; alternative visual themes; more or fewer than five categories.

## 13. Build order

Four milestones, each usable on its own:

1. **Core and print.** Data model, library, style rules, templates, single-recipe PDF from a recipe typed into the review form.
2. **Intake.** Readers, both structurers, the job queue, the Review screen.
3. **Book.** Auto-fit across the library, book assembly, editions, binding, notes lines, QR.
4. **Find and combine.** Search, ingredient lists, cookbook batch mode, inbox folder, duplicate warning.

## 14. Open items

- **Where the code lives.** This design was written in a temporary cloud workspace with no repository attached. Before the build starts, the project needs a home the Mac can pull from (a GitHub repository is the simplest).
- **Mac verification.** Apple Vision OCR, Ollama, and final print checks need the user's Mac.
- **Printing A5 in the US.** Two A5 pages do not fit side by side on a Letter sheet. Home printing needs A5 paper or trimming; a print shop handles either.
