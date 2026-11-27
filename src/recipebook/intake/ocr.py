"""Text recognition behind one small interface, so tests and Linux can use stand-ins."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

from .material import ReaderError


class Ocr(Protocol):
    def read(self, image: Path) -> str:
        """Return the text found in an image, top to bottom."""


class AppleVisionOcr:
    """macOS's built-in text recognizer. Runs offline."""

    def read(self, image: Path) -> str:
        from ocrmac import ocrmac  # imported here: the package only exists on macOS

        found = ocrmac.OCR(str(image), recognition_level="accurate", language_preference=["en-US"]).recognize()
        return "\n".join(text for text, _confidence, _box in reading_order(found))


def _column_split(boxes: list[list[float]]) -> float | None:
    """Find the gutter between two text columns: an empty vertical band between 20% and
    80% of the width, crossed by fewer than 10% of the column lines. None means one column.

    Lines wider than 45% of the page (titles, intros) cannot belong to a column, so they
    are left out of the search; reading_order treats them as band dividers."""
    boxes = [box for box in boxes if box[2] <= 0.45]
    if len(boxes) < 4:
        return None
    bins = [0] * 100
    for x, _y, width, _height in boxes:
        for b in range(max(0, int(x * 100)), min(100, int((x + width) * 100) + 1)):
            bins[b] += 1
    allowed = max(1, len(boxes) // 10)
    best, run_start = None, None
    for b in range(20, 81):
        if bins[b] <= allowed:
            run_start = b if run_start is None else run_start
            if b - run_start + 1 >= 3 and (best is None or b - run_start + 1 > best[1]):
                best = (run_start, b - run_start + 1)
        else:
            run_start = None
    return None if best is None else (best[0] + best[1] / 2) / 100


def reading_order(found: list) -> list:
    """Order recognized lines the way a person reads the page.

    Each result is (text, confidence, [x, y, width, height]) in page fractions, y measured
    from the bottom. On a two-column page, lines that span the gutter (titles, intros)
    divide the page into bands; within each band the left column is read before the right.
    """
    top_down = sorted(found, key=lambda item: (-(item[2][1] + item[2][3]), item[2][0]))
    split = _column_split([item[2] for item in found])
    if split is None:
        return top_down
    ordered, left, right = [], [], []
    for item in top_down:
        x, _y, width, _h = item[2]
        if x < split < x + width:  # spans the gutter: finish the band above it first
            ordered += left + right + [item]
            left, right = [], []
        elif x + width <= split:
            left.append(item)
        else:
            right.append(item)
    return ordered + left + right


class NoOcr:
    def read(self, image: Path) -> str:
        raise ReaderError(
            "Reading text from photos and scans needs macOS.",
            "Run the app on your Mac, or use Retry with Claude, which reads the image directly.",
        )


def default_ocr() -> Ocr:
    return AppleVisionOcr() if sys.platform == "darwin" else NoOcr()
