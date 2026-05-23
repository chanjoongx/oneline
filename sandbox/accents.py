"""Accent selection. Each tool gets exactly one accent from the approved set,
chosen to fit the tool's character, per the shared design system. This module recommends a
sensible accent per category so the candidate is always design-system valid, and
normalizes whatever accent the implementer actually wrote into the HTML.

The accent is the one place a tool expresses individuality. It is used only for
the primary action and the single most important live value. Everything else is
grayscale from the base tokens.
"""
from __future__ import annotations

from .config import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_TEAL,
    ACCENT_VIOLET,
    APPROVED_ACCENTS,
)

# Default accent per tool category, following the shared design system's category
# guidance. Keyword overrides below take priority over the category.
CATEGORY_ACCENT = {
    "timer": ACCENT_GREEN,
    "tracker": ACCENT_GREEN,
    "calculator": ACCENT_BLUE,
    "converter": ACCENT_BLUE,
    "flashcards": ACCENT_VIOLET,
    "checklist": ACCENT_BLUE,
    "decision_tool": ACCENT_VIOLET,
    "quiz": ACCENT_VIOLET,
    "single_user_game": ACCENT_VIOLET,
    "log": ACCENT_TEAL,
    "randomizer": ACCENT_TEAL,
    "planner": ACCENT_BLUE,
    "display_only": ACCENT_BLUE,
    "utility": ACCENT_TEAL,
}

# Keyword cues in the brief that override the category default.
_COUNTDOWN_CUES = ("countdown", "days until", "time left", "deadline", "until ", "remaining")
_URGENCY_CUES = ("interval", "hiit", "tabata", "workout", "sprint", "boxing", "emom", "round timer")

_APPROVED_UPPER = {a.upper(): a for a in APPROVED_ACCENTS}


def recommend_accent(tool_category: str, brief: str = "") -> str:
    """Pick one approved accent for this tool. Deterministic, always valid."""
    text = (brief or "").lower()
    if any(cue in text for cue in _COUNTDOWN_CUES):
        return ACCENT_AMBER
    if any(cue in text for cue in _URGENCY_CUES):
        return ACCENT_RED
    return CATEGORY_ACCENT.get((tool_category or "").strip().lower(), ACCENT_BLUE)


def normalize_accent(value: "str | None") -> "str | None":
    """Return the canonical approved hex for a value, or None if off-system."""
    if not value:
        return None
    v = value.strip().upper()
    if not v.startswith("#"):
        v = "#" + v
    return _APPROVED_UPPER.get(v)
