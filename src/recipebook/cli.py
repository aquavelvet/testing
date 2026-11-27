"""Command line entry point: `recipebook` and `recipebook doctor`."""

from __future__ import annotations

import argparse
import glob
import os
import sys
import threading
import webbrowser

from .config import default_home

DEFAULT_PORT = 8765
HOMEBREW_LIBRARY_FOLDERS = ("/opt/homebrew/lib", "/usr/local/lib")  # Apple Silicon, then Intel


def ensure_homebrew_libraries(argv: list[str]) -> None:
    """On a Mac, let the PDF engine find the libraries Homebrew installed (Pango and friends).

    Python from uv does not look in Homebrew's folder. macOS reads the library search path
    only when a program starts, so this sets the path and starts the program again, once.
    """
    if sys.platform != "darwin":
        return
    current = [part for part in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if part]
    for folder in HOMEBREW_LIBRARY_FOLDERS:
        if folder in current:
            return  # already set, by us or by the user; never restart twice
        if glob.glob(os.path.join(folder, "libgobject-2.0*.dylib")):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join([folder, *current])
            os.execv(sys.executable, [sys.executable, "-m", "recipebook.cli", *argv])


def serve(port: int, open_browser: bool) -> int:
    import uvicorn

    from .web.app import create_app

    home = default_home().ensure()
    url = f"http://127.0.0.1:{port}"
    print(f"Recipe Book is running at {url}")
    print(f"Your recipes live in {home.root}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(home), host="127.0.0.1", port=port, log_level="warning")
    return 0


def doctor() -> int:
    """Check that this machine can run the app. Returns 0 when every check passes."""
    results: list[tuple[bool, str, str]] = []

    def check(name: str, test) -> None:
        try:
            results.append((True, name, test() or ""))
        except Exception as error:  # a failed check is reported, never raised
            results.append((False, name, f"{type(error).__name__}: {error}"))

    def python_version() -> str:
        if sys.version_info < (3, 12):
            raise RuntimeError("Python 3.12 or newer is needed")
        return sys.version.split()[0]

    def fonts() -> str:
        from .render.pdf import FONTS

        names = sorted(p.name for p in FONTS.glob("*.ttf"))
        if len(names) != 7:
            raise RuntimeError(f"expected 7 font files in {FONTS}, found {len(names)}")
        return f"{len(names)} font files"

    def pdf_engine() -> str:
        import weasyprint

        from .model import Ingredient, IngredientGroup, Recipe, Step
        from .render.pdf import render_recipe_pdf

        sample = Recipe(
            title="Doctor's Test", category="Main Dishes",
            ingredient_groups=[IngredientGroup(items=[Ingredient(text="1 cup water")])],
            steps=[Step(text="Boil the water.")],
        )
        data, layout = render_recipe_pdf(sample)
        if not data.startswith(b"%PDF") or layout.pages != 1:
            raise RuntimeError("the test page did not render as a one-page PDF")
        return f"WeasyPrint {weasyprint.__version__}"

    def data_folder() -> str:
        from .library import Library

        home = default_home().ensure()
        probe = home.root / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        count = len(Library(home.database).list())
        return f"{home.root} ({count} recipe{'' if count == 1 else 's'})"

    check("Python", python_version)
    check("Fonts", fonts)
    check("PDF engine", pdf_engine)
    check("Data folder", data_folder)

    for ok, name, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'}  {name}: {detail}")
    for name, detail in _intake_notes():
        print(f"note  {name}: {detail}")
    failed = [name for ok, name, _ in results if not ok]
    if failed:
        print("\nIf the PDF engine failed on a Mac:")
        print("  Install Pango, then run this again:  brew install pango")
        return 1
    print("\nEverything this version needs is working.")
    return 0


def _intake_notes() -> list[tuple[str, str]]:
    """Optional pieces for reading recipes. Missing ones limit features but do not stop the app."""
    from .intake.structure import DEFAULT_LOCAL_MODEL, LocalStructurer, StructurerUnavailable
    from .library import Library
    from .secrets import KeychainStore

    notes = []
    if sys.platform == "darwin":
        try:
            import ocrmac  # noqa: F401

            notes.append(("Text recognition", "Apple Vision is available"))
        except Exception as error:
            notes.append(("Text recognition", f"not available ({type(error).__name__}); photos will need Claude"))
    else:
        notes.append(("Text recognition", "needs macOS; on this machine photos and scans need Claude"))
    try:
        model = Library(default_home().ensure().database).get_setting("local_model", DEFAULT_LOCAL_MODEL)
        LocalStructurer(model=model).check()
        notes.append(("Local model", f"Ollama is running with {model}"))
    except StructurerUnavailable as error:
        notes.append(("Local model", f"{error} {error.fix}"))
    except Exception as error:
        notes.append(("Local model", f"could not be checked ({type(error).__name__})"))
    notes.append(("Claude key", "saved" if KeychainStore().get() else "none saved; add one in Settings to use Claude"))
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recipebook", description="Recipe Book")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("serve", help="start the app (the default)")
    for target in (parser, run):
        target.add_argument("--port", type=int, default=DEFAULT_PORT)
        target.add_argument("--no-browser", action="store_true", help="do not open the browser")
    sub.add_parser("doctor", help="check that this machine can run the app")
    args = parser.parse_args(argv)
    ensure_homebrew_libraries(sys.argv[1:] if argv is None else argv)
    if args.command == "doctor":
        return doctor()
    return serve(args.port, not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
