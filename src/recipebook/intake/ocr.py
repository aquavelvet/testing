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
        # Each result is (text, confidence, [x, y, width, height]) with y measured from the bottom.
        lines = sorted(found, key=lambda item: (-round(item[2][1] + item[2][3], 2), item[2][0]))
        return "\n".join(text for text, _confidence, _box in lines)


class NoOcr:
    def read(self, image: Path) -> str:
        raise ReaderError(
            "Reading text from photos and scans needs macOS.",
            "Run the app on your Mac, or use Retry with Claude, which reads the image directly.",
        )


def default_ocr() -> Ocr:
    return AppleVisionOcr() if sys.platform == "darwin" else NoOcr()
