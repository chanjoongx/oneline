"""Configuration for the Oneline judges.

The three model based judges and the curator all use gemini-3.5-flash, no other
model. The API key is read from the environment only, never stored here. No em
dashes anywhere, hyphens only.
"""
from __future__ import annotations

import os
from pathlib import Path

# Paths. The repo root is the parent of the judges/ package directory.
JUDGES_DIR = Path(__file__).resolve().parent
REPO_ROOT = JUDGES_DIR.parent
SHARED_DIR = REPO_ROOT / "shared"
SCHEMA_DIR = SHARED_DIR / "schemas"

# Every product model call is gemini-3.5-flash. The env var exists only for local
# testing; never point it at a non-Gemini model in the product.
MODEL = os.environ.get("ONELINE_MODEL", "gemini-3.5-flash")

# The Managed Agents agent id. Confirmed against the live docs (the Continue the
# conversation section of the managed agents quickstart): a sandbox is reused by
# calling interactions.create(agent=AGENT, environment=<existing_environment_id>,
# input=...). The build sandbox and the functionality test share this agent, so
# the test runs in the very sandbox the candidate was built in.
AGENT = os.environ.get("ONELINE_AGENT", "antigravity-preview-05-2026")

# Thinking budgets per level, in tokens. Shared with core via the same env var
# names so the whole product stays consistent. UX clarity runs high, design
# coherence runs medium, the curator runs high.
THINKING_BUDGET = {
    "low": int(os.environ.get("ONELINE_THINK_LOW", "1024")),
    "medium": int(os.environ.get("ONELINE_THINK_MEDIUM", "6144")),
    "high": int(os.environ.get("ONELINE_THINK_HIGH", "16384")),
}

# Mobile viewport the functionality judge renders at. iPhone Safari width, a
# tall single screen held in one hand.
VIEWPORT = {"width": 390, "height": 844}

# How many extra interactive controls the functionality test exercises after the
# primary action, to confirm the interface stays responsive.
CLICK_BUDGET = 8

# The six approved accents of the shared design system. The design judge
# references these so a second accent or any off-system color is caught. One
# accent per tool, assigned to --accent, used only for the primary action and the
# single most important live value.
APPROVED_ACCENTS = [
    ("#5B8DEF", "blue", "default, neutral, planners, calculators"),
    ("#3FB950", "green", "trackers, habits, progress, timers counting up"),
    ("#E3A008", "amber", "countdowns, reminders, time pressure"),
    ("#A371F7", "violet", "learning, flashcards, focus"),
    ("#F85149", "red", "intervals, workouts, urgency, use sparingly"),
    ("#2DD4BF", "teal", "logs, notes, calm utilities"),
]

APPROVED_ACCENT_HEXES = [hex_value for hex_value, _name, _fit in APPROVED_ACCENTS]

# The non-accent base tokens of the shared design system. Any color outside this
# set and the approved accents is off-system and the design judge flags it. The
# feedback colors (positive, warning, danger) are allowed only in their semantic
# status roles, never as a second accent.
BASE_TOKEN_HEXES = {
    "--bg": "#0A0A0B",
    "--surface": "#141416",
    "--surface-2": "#1C1C1F",
    "--border": "#2A2A2E",
    "--text": "#F5F5F7",
    "--text-muted": "#9A9AA2",
    "--text-faint": "#5C5C64",
    "--accent-ink": "#0A0A0B",
    "--positive": "#3FB950",
    "--warning": "#D29922",
    "--danger": "#F85149",
}

# How much HTML to send to the model judges. Generated tools are single file and
# usually small; this caps token use on the rare large one.
MAX_HTML_CHARS = int(os.environ.get("ONELINE_JUDGE_MAX_HTML", "24000"))


def gemini_api_key() -> "str | None":
    """Read the Gemini API key from the environment. Never hardcode or log it."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
