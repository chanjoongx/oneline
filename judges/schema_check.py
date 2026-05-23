"""Validate judge and curator outputs against the shared contract in shared/.

The judges code against the schemas the core module committed. This module reads
those files (read only, the judges never edit shared/) and validates that every
JudgeScores object and curator output matches the contract before it leaves the
judges layer. jsonschema is imported lazily so the package imports even where it
is not installed; when it is absent the validators degrade to a permissive pass.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import SCHEMA_DIR

_JUDGE_SCORES_FILE = "judge_scores.schema.json"
_LESSON_FILE = "lesson.schema.json"


@lru_cache(maxsize=None)
def _load(filename: str) -> dict:
    with open(SCHEMA_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _validator(filename: str):
    from jsonschema import Draft202012Validator

    return Draft202012Validator(_load(filename))


@lru_cache(maxsize=None)
def _curator_validator():
    from jsonschema import Draft202012Validator

    lesson = _load(_LESSON_FILE)
    subschema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": lesson["$defs"],
        "$ref": "#/$defs/curator_output",
    }
    return Draft202012Validator(subschema)


def validate_judge_scores(obj: Any) -> None:
    """Raise if obj does not match the shared JudgeScores schema."""
    _validator(_JUDGE_SCORES_FILE).validate(obj)


def is_valid_judge_scores(obj: Any) -> bool:
    try:
        _validator(_JUDGE_SCORES_FILE).validate(obj)
        return True
    except Exception:
        return False


def validate_curator_output(obj: Any) -> None:
    """Raise if obj does not match the curator_output subschema of Lesson."""
    _curator_validator().validate(obj)


def is_valid_curator_output(obj: Any) -> bool:
    try:
        _curator_validator().validate(obj)
        return True
    except Exception:
        return False


# The shared vocabulary, mirrored from shared/schemas/lesson.schema.json so the
# curator can coerce model output onto the exact enums the retriever matches by.
TOOL_CATEGORIES = [
    "timer", "tracker", "calculator", "flashcards", "checklist", "decision_tool",
    "quiz", "single_user_game", "log", "converter", "randomizer", "planner",
    "display_only", "utility",
]

LESSON_CLASSES = ["functionality", "ux_clarity", "design_coherence"]

ANTI_PATTERNS = [
    "buried_primary_action", "cluttered_layout", "tiny_touch_targets",
    "ambiguous_cta", "missing_feedback_state", "generic_button_text",
    "thumb_unreachable", "overflow_scrolling", "hidden_state",
    "production_app_smell", "palette_drift", "typography_inconsistency",
    "cluttered_spacing", "low_contrast",
]

SEVERITIES = ["low", "medium", "high"]

# Always-on mobile tags from the shared vocabulary, ensured on every lesson so the
# tag based retriever can always find broadly applicable lessons.
ALWAYS_ON_TAGS = [
    "mobile_first", "touch_targets", "primary_cta", "thumb_zone", "single_screen",
]
