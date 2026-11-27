"""The watched inbox folder: files dropped in are queued by themselves."""

from __future__ import annotations

import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

from .jobs import Job, JobStore

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
SETTLE_SECONDS = 2.0
SCAN_EVERY_SECONDS = 5.0


class InboxWatcher:
    def __init__(self, inbox: Path, originals: Path, jobs: JobStore, default_structurer: Callable[[], str]):
        self.inbox, self.originals, self.jobs = Path(inbox), Path(originals), jobs
        self.default_structurer = default_structurer
        self._seen: dict[Path, tuple[int, float]] = {}  # path -> (size, when that size was first seen)
        self._last_scan = 0.0

    def scan(self, now: float | None = None) -> list[Job]:
        """Queue every supported file whose size has stopped changing. Other files are left alone."""
        now = time.time() if now is None else now
        if now - self._last_scan < SCAN_EVERY_SECONDS:
            return []
        self._last_scan = now
        added: list[Job] = []
        present = set()
        for path in sorted(self.inbox.iterdir()) if self.inbox.is_dir() else []:
            suffix = path.suffix.lower()
            if not path.is_file() or path.name.startswith(".") or (suffix != ".pdf" and suffix not in PHOTO_TYPES):
                continue
            present.add(path)
            size = path.stat().st_size
            seen = self._seen.get(path)
            if seen is None or seen[0] != size:
                self._seen[path] = (size, now)  # new, or still being copied in
                continue
            if size == 0 or now - seen[1] < SETTLE_SECONDS:
                continue
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-") or "file"
            target = self.originals / f"{uuid.uuid4().hex[:8]}-{safe}{suffix}"
            self.originals.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), target)
            added.append(self.jobs.add(Job(kind="pdf" if suffix == ".pdf" else "photo", label=path.name,
                                           files=[str(target)], structurer=self.default_structurer())))
            present.discard(path)
        self._seen = {path: seen for path, seen in self._seen.items() if path in present}
        return added
