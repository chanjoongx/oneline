"""Knowledge base I/O. Read and write shared/knowledge_base.json.

Core is the only writer. The curator in judges/ returns a curator_output;
core enriches it into a stored Lesson (adds id, created_at, applied_count 0,
prevented_repeats 0) and appends it. Writes are atomic via a temp file.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import schemas
from .config import KB_PATH


def read_kb(path=KB_PATH) -> dict:
    """Read the knowledge base. Returns {"lessons": [...]}."""
    p = Path(path)
    if not p.exists():
        return {"lessons": []}
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("lessons", [])
    return data


def list_lessons(path=KB_PATH) -> list:
    """Return the list of stored lessons."""
    return read_kb(path)["lessons"]


def _write_kb(data: dict, path=KB_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def next_lesson_id(lessons: list) -> str:
    """Return the next sequential lesson id, for example lesson_002."""
    highest = 0
    for lesson in lessons:
        ident = lesson.get("id", "")
        if ident.startswith("lesson_"):
            try:
                highest = max(highest, int(ident.split("_")[1]))
            except (IndexError, ValueError):
                pass
    return f"lesson_{highest + 1:03d}"


def append_lesson(curator_output: dict, path=KB_PATH, validate: bool = True):
    """Enrich a curator output into a stored Lesson and append it.

    Returns the stored Lesson, or None when curator_output is None (the curator
    found nothing generalizable).
    """
    if curator_output is None:
        return None
    if validate:
        schemas.validate_curator_output(curator_output)
    data = read_kb(path)
    lesson = dict(curator_output)
    lesson["id"] = next_lesson_id(data["lessons"])
    lesson["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lesson.setdefault("applied_count", 0)
    lesson.setdefault("prevented_repeats", 0)
    if validate:
        schemas.validate(lesson, "lesson")
    data["lessons"].append(lesson)
    _write_kb(data, path)
    return lesson


def _bump(field: str, ids: list, path=KB_PATH) -> None:
    if not ids:
        return
    data = read_kb(path)
    targets = set(ids)
    for lesson in data["lessons"]:
        if lesson.get("id") in targets:
            lesson[field] = int(lesson.get(field, 0)) + 1
    _write_kb(data, path)


def bump_applied(ids: list, path=KB_PATH) -> None:
    """Increment applied_count for lessons that were injected into a build."""
    _bump("applied_count", ids, path)


def bump_prevented(ids: list, path=KB_PATH) -> None:
    """Increment prevented_repeats for lessons whose anti-pattern was avoided."""
    _bump("prevented_repeats", ids, path)
