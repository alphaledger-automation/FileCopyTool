"""
File Copy Tool — Copy Engine
============================
The part that actually moves bytes. It knows nothing about the GUI: it
posts tuples onto a queue and the window drains them.

Messages put on `out_q`:
    ("log",     level, text)          level in {info, ok, warn, err}
    ("record",  Record)               one row changed — redraw it
    ("current", relative_path)        what is being copied right now
    ("done",)                         the run finished (or was cancelled)
"""

from __future__ import annotations

import os
import pathlib
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from constants import (
    IF_EXISTS_OVERWRITE, IF_EXISTS_RENAME, IF_EXISTS_SKIP,
    MATCH_SMART,
    RES_CANCELLED, RES_COPIED, RES_COPYING, RES_FAILED, RES_MISSING,
    RES_PENDING, RES_SKIPPED,
)


# ── One line of the list ─────────────────────────────────────────────────────

@dataclass
class Record:
    idx: int                        # 1-based row number
    name: str                       # the line as written in the list
    result: str = RES_PENDING
    size: int = 0                   # bytes copied
    source_path: str = ""           # what was matched in the source
    dest_path: str = ""             # where it landed
    note: str = ""                  # short human explanation

    @property
    def size_text(self) -> str:
        return human_size(self.size) if self.size else ""

    @property
    def found_as(self) -> str:
        """The matched file name, shown when it differs from the line."""
        if not self.source_path:
            return ""
        matched = os.path.basename(self.source_path)
        return "" if matched == os.path.basename(self.name) else matched


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:,.0f} {unit}" if unit == "B" else f"{num:,.1f} {unit}"
        num /= 1024.0
    return f"{num:,.1f} TB"


# ── Reading the list ─────────────────────────────────────────────────────────

def parse_lines(raw: str) -> List[str]:
    """
    Turn raw text into clean file names.

      * blank lines are dropped
      * a leading '#' marks a comment
      * surrounding quotes and stray commas / semicolons are stripped
      * duplicates are kept (the user may genuinely want two copies)
    """
    out: List[str] = []
    for line in raw.splitlines():
        line = line.strip().strip("﻿")
        if not line or line.startswith("#"):
            continue
        # A line pasted out of Excel or code can arrive as  "name.pdf",
        # so peel quotes and separators off until nothing changes.
        while True:
            before = line
            line = line.rstrip(",;").strip()
            if len(line) > 1 and line[0] == line[-1] and line[0] in "\"'":
                line = line[1:-1].strip()
            if line == before:
                break
        if line:
            out.append(line)
    return out


def read_list_file(path: str) -> List[str]:
    """Read a .txt / .csv list, tolerating whatever encoding Windows used."""
    data = pathlib.Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return parse_lines(data.decode(encoding))
        except (UnicodeDecodeError, UnicodeError):
            continue
    return parse_lines(data.decode("utf-8", errors="replace"))


def build_records(names: List[str]) -> List[Record]:
    return [Record(idx=i, name=n) for i, n in enumerate(names, start=1)]


# ── Finding a file in the source folder ──────────────────────────────────────

def _index_source(source: pathlib.Path, recursive: bool) -> dict:
    """
    name (lowercased) -> full path, plus stem -> full path, so a line can be
    matched with or without its extension. Built once per run.
    """
    index: dict = {}
    walker = source.rglob("*") if recursive else source.glob("*")
    for path in walker:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        index.setdefault(path.name.lower(), path)
        index.setdefault(path.stem.lower(), path)
    return index


def resolve_source(name: str, source: pathlib.Path, index: Optional[dict],
                   smart: bool) -> Optional[pathlib.Path]:
    """Work out which real file a list line refers to."""
    direct = source / name
    try:
        if direct.is_file():
            return direct
    except OSError:
        pass
    if not smart or index is None:
        return None
    key = os.path.basename(name).lower()
    hit = index.get(key)
    if hit is not None:
        return hit
    return index.get(pathlib.Path(key).stem)


def unique_path(path: pathlib.Path) -> pathlib.Path:
    """file.pdf -> file (2).pdf -> file (3).pdf ..."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


# ── The worker ───────────────────────────────────────────────────────────────

class CopyWorker:
    """
    Runs the copy on a background thread. Create it, hand it a queue and
    two events, then call run() from the thread.
    """

    def __init__(self, records: List[Record], source_dir: pathlib.Path,
                 dest_dir: pathlib.Path, out_q, stop_event: threading.Event,
                 pause_event: threading.Event,
                 if_exists: str = IF_EXISTS_OVERWRITE,
                 match_mode: str = MATCH_SMART,
                 recursive: bool = True,
                 flatten: bool = False):
        self.records = records
        self.source_dir = pathlib.Path(source_dir)
        self.dest_dir = pathlib.Path(dest_dir)
        self.q = out_q
        self.stop_event = stop_event
        self.pause_event = pause_event          # SET = paused
        self.if_exists = if_exists
        self.match_mode = match_mode
        self.recursive = recursive
        self.flatten = flatten

        self.copied = 0
        self.skipped = 0
        self.missing = 0
        self.failed = 0
        self.bytes_copied = 0

    # ── queue helpers ───────────────────────────────────────────────────
    def _log(self, text: str, level: str = "info") -> None:
        self.q.put(("log", level, text))

    def _push(self, rec: Record) -> None:
        self.q.put(("record", rec))

    def _wait_if_paused(self) -> None:
        while self.pause_event.is_set() and not self.stop_event.is_set():
            time.sleep(0.1)

    # ── main loop ───────────────────────────────────────────────────────
    def run(self) -> None:
        total = len(self.records)
        smart = self.match_mode == MATCH_SMART

        try:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:                        # noqa: BLE001
            self._log(f"Cannot create the destination folder: {exc}", "err")
            self.q.put(("done",))
            return

        self._log(f"Source      : {self.source_dir}")
        self._log(f"Destination : {self.dest_dir}")
        self._log(f"Files listed: {total:,}")

        index = None
        if smart:
            self._log("Indexing the source folder ...")
            try:
                index = _index_source(self.source_dir, self.recursive)
                self._log(f"Indexed {len(index):,} name(s) in the source.", "ok")
            except Exception as exc:                    # noqa: BLE001
                self._log(f"Could not index the source folder: {exc}", "warn")
                index = {}

        for rec in self.records:
            if self.stop_event.is_set():
                rec.result = RES_CANCELLED
                self._push(rec)
                continue

            self._wait_if_paused()
            if self.stop_event.is_set():
                rec.result = RES_CANCELLED
                self._push(rec)
                continue

            rec.result = RES_COPYING
            self._push(rec)
            self.q.put(("current", rec.name))

            try:
                self._copy_one(rec, index, smart)
            except Exception as exc:                    # noqa: BLE001
                rec.result = f"{RES_FAILED} - {exc}"
                rec.note = str(exc)
                self.failed += 1
                self._log(f"[{rec.idx}/{total}] {rec.name} - failed: {exc}", "err")

            self._push(rec)

        self._summary(total)
        self.q.put(("done",))

    # ── one file ────────────────────────────────────────────────────────
    def _copy_one(self, rec: Record, index, smart: bool) -> None:
        total = len(self.records)
        src = resolve_source(rec.name, self.source_dir, index, smart)

        if src is None:
            rec.result = RES_MISSING
            rec.note = "not found in the source folder"
            self.missing += 1
            self._log(f"[{rec.idx}/{total}] {rec.name} - not found in source",
                      "warn")
            return

        rec.source_path = str(src)

        # Where it goes: keep the sub-folder the list line asked for, unless
        # the user chose to flatten everything into one folder.
        rel = pathlib.Path(rec.name)
        if self.flatten or rel.is_absolute() or ".." in rel.parts:
            dst = self.dest_dir / src.name
        elif rel.parent != pathlib.Path("."):
            dst = self.dest_dir / rel.parent / src.name
        else:
            dst = self.dest_dir / src.name

        if dst.exists():
            if self.if_exists == IF_EXISTS_SKIP:
                rec.result = RES_SKIPPED
                rec.dest_path = str(dst)
                rec.note = "already in the destination"
                self.skipped += 1
                self._log(f"[{rec.idx}/{total}] {rec.name} - already there, "
                          f"skipped", "info")
                return
            if self.if_exists == IF_EXISTS_RENAME:
                dst = unique_path(dst)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        rec.dest_path = str(dst)
        try:
            rec.size = dst.stat().st_size
        except OSError:
            rec.size = 0
        rec.result = RES_COPIED
        rec.note = ""
        self.copied += 1
        self.bytes_copied += rec.size

        extra = f"  (found as {src.name})" if rec.found_as else ""
        self._log(f"[{rec.idx}/{total}] {rec.name} - copied, "
                  f"{rec.size_text}{extra}", "ok")

    # ── closing block in the log ────────────────────────────────────────
    def _summary(self, total: int) -> None:
        self._log("")
        self._log("SUMMARY")
        self._log(f"   Listed   : {total:,}")
        self._log(f"   Copied   : {self.copied:,}  ({human_size(self.bytes_copied)})",
                  "ok" if self.copied else "info")
        if self.skipped:
            self._log(f"   Skipped  : {self.skipped:,}")
        if self.missing:
            self._log(f"   Missing  : {self.missing:,}", "warn")
        if self.failed:
            self._log(f"   Failed   : {self.failed:,}", "err")
        if self.stop_event.is_set():
            self._log("Run cancelled before the end of the list.", "warn")
