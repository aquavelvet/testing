# Recipe Book

A local app that takes recipes from web pages, PDFs, and cookbook photos, puts each one into a single house format, and prints them as A5 pages: one PDF per recipe, or a full recipe book.

Status: milestone 3 of 4 (core, print, intake, and the full book with contents, sections, and index).

## Requirements

- macOS on Apple Silicon (development and tests also run on Linux)
- [uv](https://docs.astral.sh/uv/)
- Pango, which the PDF engine needs:

```bash
brew install pango
```

## Reading recipes

- **Local model (offline).** Install [Ollama](https://ollama.com), then download the default model:

```bash
ollama pull qwen2.5:7b
```

- **Claude (optional).** Add your Anthropic API key on the app's Settings page. It is kept in the macOS Keychain. Claude is only called when you choose it.
- **Photos and scans** are read with macOS's built-in text recognition, so that part only works on a Mac.

To compare models on your own recipes, see `src/recipebook/intake/evaluate.py`.

## Run

```bash
uv run recipebook
```

The app opens in your browser at `http://127.0.0.1:8765`. Your recipes live in `~/RecipeBook/`.

Check the machine setup:

```bash
uv run recipebook doctor
```

If the PDF engine check fails with a message about a library such as `libgobject`, Python cannot see Homebrew's libraries. Point it at them, then run the check again:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

## Test

```bash
uv run pytest
```
