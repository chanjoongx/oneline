"""Configuration for the Oneline sandbox module.

This package owns the Gemini Managed Agents integration: it spawns one isolated
sandbox per candidate, runs the implementer prompt inside it, and returns a
Candidate (shared/schemas/candidate.schema.json). The functionality judge later
reuses each candidate's environment_id to run Playwright in the very sandbox the
tool was built in.

No secret lives here. The API key is read from the environment only.
"""
from __future__ import annotations

import os
from pathlib import Path

# Paths. Repo root is the parent of this package directory.
SANDBOX_DIR = Path(__file__).resolve().parent
REPO_ROOT = SANDBOX_DIR.parent
SHARED_DIR = REPO_ROOT / "shared"
SCHEMA_DIR = SHARED_DIR / "schemas"
BASE_CSS_PATH = SHARED_DIR / "base.css"
CANDIDATE_SCHEMA_PATH = SCHEMA_DIR / "candidate.schema.json"

# Managed Agents call. Confirmed working shape (tested, google-genai upgraded):
#   client.interactions.create(agent=AGENT, input=prompt, environment="remote")
# returns .output_text, .id, .environment_id, .steps. The sandbox is reused by
# passing environment=<environment_id> on a later create call.
AGENT = os.environ.get("ONELINE_AGENT", "antigravity-preview-05-2026")
REMOTE_ENV = "remote"

# Product intelligence is gemini-3.5-flash for every model call, no exceptions.
# The implementer runs gemini-3.5-flash inside the managed agent. Passed to the
# create call when the SDK accepts it; the agent otherwise carries the model.
IMPLEMENTER_MODEL = os.environ.get("ONELINE_MODEL", "gemini-3.5-flash")

# Output token cap for interactions.create. The default model cap (around 8192
# tokens, roughly 32KB of text) truncates larger self-contained tools mid-script.
# We raise it so a complete single-file HTML tool always fits. Tune day-of if the
# model reports a different ceiling.
MAX_OUTPUT_TOKENS = int(os.environ.get("ONELINE_MAX_OUTPUT_TOKENS", "32768"))

# Sandbox file system. The functionality judge writes the candidate and its test
# here, runs the test, and saves a screenshot to a known path so it is never null.
SANDBOX_WORKDIR = "/work"
DEFAULT_TOOL_PATH = SANDBOX_WORKDIR + "/tool.html"
DEFAULT_SCREENSHOT_PATH = SANDBOX_WORKDIR + "/screenshot.png"

# Approved accent palette. Pick exactly one per tool. These hex values match the
# enum in shared/schemas/candidate.schema.json verbatim (uppercase).
ACCENT_BLUE = "#5B8DEF"
ACCENT_GREEN = "#3FB950"
ACCENT_AMBER = "#E3A008"
ACCENT_VIOLET = "#A371F7"
ACCENT_RED = "#F85149"
ACCENT_TEAL = "#2DD4BF"

APPROVED_ACCENTS = (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_AMBER,
    ACCENT_VIOLET,
    ACCENT_RED,
    ACCENT_TEAL,
)


def gemini_api_key() -> "str | None":
    """Read the Gemini API key from the environment. Never hardcode or log it."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
