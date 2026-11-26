"""Compare models on your own recipes, to choose the default local model.

    uv run python -m recipebook.intake.evaluate ~/RecipeBook/evaluation --models qwen2.5:7b,llama3.1:8b --claude

The folder holds photos, PDFs, and an optional urls.txt (one address per line). For each
input and model this prints how many recipes were found, how many amount warnings the
fidelity check raised, and how long it took. Drafts are written beside the inputs as JSON
so they can be compared by eye with the originals.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from ..model import DEFAULT_CATEGORIES
from ..secrets import KeychainStore
from ..style.glossary import DEFAULT_GLOSSARY
from .material import ReaderError
from .ocr import default_ocr
from .pipeline import finish_draft
from .readers import read_pdf, read_photos, read_url
from .structure import ClaudeStructurer, LocalStructurer, StructurerError, StructurerUnavailable

PHOTOS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--models", default="qwen2.5:7b", help="comma-separated Ollama model names")
    parser.add_argument("--claude", action="store_true", help="also run Claude (uses your saved key; costs money)")
    args = parser.parse_args(argv)

    structurers = [(name, LocalStructurer(model=name)) for name in args.models.split(",") if name.strip()]
    if args.claude:
        structurers.append(("claude", ClaudeStructurer(api_key=KeychainStore().get())))

    inputs: list[tuple[str, object]] = []
    urls = args.folder / "urls.txt"
    if urls.exists():
        inputs += [(line.strip(), "url") for line in urls.read_text().splitlines() if line.strip()]
    for path in sorted(args.folder.iterdir()):
        if path.suffix.lower() == ".pdf":
            inputs.append((path.name, path))
        elif path.suffix.lower() in PHOTOS:
            inputs.append((path.name, path))
    if not inputs:
        print(f"No photos, PDFs, or urls.txt found in {args.folder}")
        return 1

    out = args.folder / "results"
    out.mkdir(exist_ok=True)
    ocr = default_ocr()
    print(f"{'input':32.32}  {'model':16.16}  recipes  amount warnings  seconds")
    with tempfile.TemporaryDirectory() as scratch:
        for label, item in inputs:
            try:
                if item == "url":
                    material = read_url(label, Path(scratch))
                elif Path(item).suffix.lower() == ".pdf":
                    material = read_pdf(Path(item), Path(scratch), ocr)
                else:
                    material = read_photos([Path(item)], Path(scratch), ocr)
            except ReaderError as error:
                print(f"{label:32.32}  could not be read: {error}")
                continue
            for name, structurer in structurers:
                started = time.time()
                try:
                    recipes = structurer.structure(material, DEFAULT_CATEGORIES, DEFAULT_GLOSSARY)
                except (StructurerError, StructurerUnavailable) as error:
                    print(f"{label:32.32}  {name:16.16}  failed: {error}")
                    continue
                drafts = [finish_draft(r, material.text, DEFAULT_GLOSSARY) for r in recipes]
                warnings = sum(1 for d in drafts for f in d.flags if f.kind == "amount_changed")
                print(f"{label:32.32}  {name:16.16}  {len(drafts):7d}  {warnings:15d}  {time.time() - started:7.1f}")
                safe = "".join(c if c.isalnum() else "-" for c in f"{label}--{name}")[:120]
                (out / f"{safe}.json").write_text(
                    json.dumps([json.loads(d.model_dump_json(exclude={"original_text"})) for d in drafts],
                               indent=2, ensure_ascii=False))
    print(f"\nDrafts written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
