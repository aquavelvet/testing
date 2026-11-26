# Recipe Book

A local app that takes recipes from web pages, PDFs, and cookbook photos, puts each one into a single house format, and prints them as A5 pages: one PDF per recipe, or a full recipe book.

Status: milestone 1 of 4 (core and print). See `docs/superpowers/specs/` for the design and `docs/superpowers/plans/` for the plan.

## Requirements

- macOS on Apple Silicon (development and tests also run on Linux)
- [uv](https://docs.astral.sh/uv/)
- Pango, which the PDF engine needs:

```bash
brew install pango
```

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
