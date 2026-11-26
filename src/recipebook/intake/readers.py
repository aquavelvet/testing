"""Readers turn an input (URL, PDF, photos) into SourceMaterial."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pypdfium2 as pdfium
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from ..model import Source, format_minutes
from .material import ReaderError, SourceMaterial
from .ocr import Ocr

MAX_PDF_PAGES = 10
MAX_IMAGE_EDGE = 2000
FETCH_TIMEOUT = 20.0
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
_SAVE_AS_PDF = "Open the page in your browser, save it as a PDF or take a screenshot, and add that instead."


def _unique(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "file"
    return folder / f"{uuid.uuid4().hex[:8]}-{safe}"


# ---------------------------------------------------------------- URL

def _iso_minutes(value) -> int | None:
    """PT1H30M -> 90."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?", str(value or "").strip(), re.IGNORECASE)
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g or 0) for g in match.groups())
    return days * 1440 + hours * 60 + minutes


def _as_text(value) -> str:
    if isinstance(value, dict):
        value = value.get("text") or value.get("name") or ""
    if isinstance(value, list):
        return ", ".join(_as_text(v) for v in value if v)
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def _find_recipe(node):
    """Find the schema.org Recipe object anywhere inside parsed JSON-LD."""
    if isinstance(node, list):
        for item in node:
            found = _find_recipe(item)
            if found:
                return found
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Recipe" in kinds:
            return node
        return _find_recipe(node.get("@graph"))
    return None


def _instructions(node, lines: list[str]) -> None:
    if isinstance(node, str):
        lines.extend(part.strip() for part in re.split(r"\n+", _as_text(node)) if part.strip())
    elif isinstance(node, list):
        for item in node:
            _instructions(item, lines)
    elif isinstance(node, dict):
        if node.get("@type") == "HowToSection":
            if node.get("name"):
                lines.append(f"{_as_text(node['name'])}:")
            _instructions(node.get("itemListElement"), lines)
        else:
            text = _as_text(node)
            if text:
                lines.append(text)


def recipe_data_to_text(data: dict) -> str:
    """Write embedded recipe data out as plain text, the same shape a person would read."""
    lines = [_as_text(data.get("name"))]
    if data.get("description"):
        lines += ["", _as_text(data["description"])]
    facts = []
    if data.get("recipeYield"):
        yields = data["recipeYield"]
        facts.append(f"Yield: {_as_text(yields[0] if isinstance(yields, list) else yields)}")
    for label, key in (("Prep time", "prepTime"), ("Cook time", "cookTime"), ("Total time", "totalTime")):
        minutes = _iso_minutes(data.get(key))
        if minutes:
            facts.append(f"{label}: {format_minutes(minutes)}")
    if facts:
        lines += ["", *facts]
    ingredients = [_as_text(item) for item in data.get("recipeIngredient") or data.get("ingredients") or []]
    lines += ["", "Ingredients:", *[i for i in ingredients if i]]
    steps: list[str] = []
    _instructions(data.get("recipeInstructions"), steps)
    lines += ["", "Directions:", *steps]
    return "\n".join(lines).strip()


def _page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    lines = [line.strip() for line in main.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def read_url(url: str, originals: Path, client: httpx.Client | None = None) -> SourceMaterial:
    url = url.strip()
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise ReaderError(f"“{url}” is not a web address.", "A web address starts with https://")
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT, headers={"User-Agent": _USER_AGENT})
    try:
        response = client.get(url)
    except httpx.TimeoutException:
        raise ReaderError("The site took too long to answer.", _SAVE_AS_PDF) from None
    except httpx.HTTPError as error:
        raise ReaderError(f"The page could not be fetched ({type(error).__name__}).", _SAVE_AS_PDF) from None
    finally:
        if own_client:
            client.close()
    if response.status_code >= 400:
        raise ReaderError(f"The site refused the request (error {response.status_code}).", _SAVE_AS_PDF)

    snapshot = _unique(originals, (urlsplit(url).hostname or "page") + ".html")
    snapshot.write_text(response.text, encoding="utf-8")
    soup = BeautifulSoup(response.text, "html.parser")
    source = Source(kind="web", url=url)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _find_recipe(json.loads(script.string or script.get_text() or ""))
        except (json.JSONDecodeError, TypeError):
            continue
        if data and (data.get("recipeIngredient") or data.get("ingredients")):
            return SourceMaterial(kind="url", text=recipe_data_to_text(data), has_recipe_data=True,
                                  files=[str(snapshot)], source=source)

    text = _page_text(soup)
    if len(text) < 200:
        raise ReaderError("The page has almost no readable text. It may need a login or load its content later.",
                          _SAVE_AS_PDF)
    return SourceMaterial(kind="url", text=text, files=[str(snapshot)], source=source)


# ---------------------------------------------------------------- images

def _save_jpeg(image: Image.Image, target: Path) -> Path:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    image.save(target, "JPEG", quality=88)
    return target


def _open_image(path: Path) -> Image.Image:
    if path.suffix.lower() in (".heic", ".heif"):
        import pillow_heif

        pillow_heif.register_heif_opener()
    try:
        return Image.open(path)
    except Exception:
        raise ReaderError(f"“{path.name}” could not be opened as an image.",
                          "Use a JPEG, PNG, or HEIC photo, or a PDF.") from None


def _ocr_all(images: list[Path], ocr: Ocr) -> tuple[str, list[str]]:
    """OCR every image. A missing recognizer is a warning, not a failure: Claude can still read the images."""
    texts, warnings = [], []
    for image in images:
        try:
            texts.append(ocr.read(image).strip())
        except ReaderError as error:
            warnings.append(str(error))
            break
    return "\n\n".join(t for t in texts if t), warnings


def read_photos(paths: list[Path], originals: Path, ocr: Ocr, source: Source | None = None) -> SourceMaterial:
    """One or more photos of the same recipe, in reading order."""
    if not paths:
        raise ReaderError("No photos were given.")
    images = [_save_jpeg(_open_image(Path(p)), _unique(originals, Path(p).stem + ".jpg")) for p in paths]
    text, warnings = _ocr_all(images, ocr)
    return SourceMaterial(kind="photo", text=text, images=[str(i) for i in images],
                          files=[str(p) for p in paths], source=source or Source(), warnings=warnings)


# ---------------------------------------------------------------- PDF

def parse_page_range(text: str, page_count: int) -> list[int]:
    """'3-7' or '4' -> zero-based page indexes. Empty means every page."""
    text = (text or "").strip()
    if not text:
        return list(range(page_count))
    match = re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?", text)
    if not match:
        raise ReaderError(f"“{text}” is not a page range.", "Write a range like 3-7, or a single page like 4.")
    first, last = int(match.group(1)), int(match.group(2) or match.group(1))
    if first < 1 or last < first or last > page_count:
        raise ReaderError(f"Pages {text} are outside this PDF, which has {page_count} pages.")
    return list(range(first - 1, last))


def read_pdf(path: Path, originals: Path, ocr: Ocr, pages: str = "", source: Source | None = None) -> SourceMaterial:
    path = Path(path)
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception:
        raise ReaderError(f"“{path.name}” could not be opened as a PDF.") from None
    indexes = parse_page_range(pages, len(pdf))
    if len(indexes) > MAX_PDF_PAGES:
        raise ReaderError(
            f"This PDF has {len(indexes)} pages; one intake covers up to {MAX_PDF_PAGES}.",
            f"Add it again with a page range of {MAX_PDF_PAGES} pages or fewer, for example 1-{MAX_PDF_PAGES}.")

    images, layer_text = [], []
    for index in indexes:
        page = pdf[index]
        layer_text.append(page.get_textpage().get_text_range().strip())
        rendered = page.render(scale=200 / 72).to_pil()
        images.append(_save_jpeg(rendered, _unique(originals, f"{path.stem}-p{index + 1}.jpg")))

    text, warnings = "\n\n".join(t for t in layer_text if t), []
    if len(text) < 50 * len(indexes):  # a scan: almost nothing in the text layer
        text, warnings = _ocr_all(images, ocr)
    return SourceMaterial(kind="pdf", text=text, images=[str(i) for i in images], files=[str(path)],
                          source=source or Source(), warnings=warnings)
