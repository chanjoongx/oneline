"""Configuration for Oneline core. Paths, the model, thinking budgets, and the
selector and retriever constants. No secret is ever stored here; the API key is
read from the environment only.
"""
from __future__ import annotations

import os
from pathlib import Path

# Paths. Repo root is the parent of the core/ package directory.
CORE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CORE_DIR.parent
SHARED_DIR = REPO_ROOT / "shared"
SCHEMA_DIR = SHARED_DIR / "schemas"
KB_PATH = SHARED_DIR / "knowledge_base.json"

# Product intelligence is gemini-3.5-flash for every model call. The env var is
# only for local testing; never point it at a non-Gemini model in the product.
MODEL = os.environ.get("ONELINE_MODEL", "gemini-3.5-flash")

# Thinking budgets per level, in tokens. These are a working assumption for
# gemini-3.5-flash and should be confirmed against the live API, then tuned.
THINKING_BUDGET = {
    "low": int(os.environ.get("ONELINE_THINK_LOW", "1024")),
    "medium": int(os.environ.get("ONELINE_THINK_MEDIUM", "6144")),
    "high": int(os.environ.get("ONELINE_THINK_HIGH", "16384")),
}

# Retriever
RETRIEVER_TOP_K = int(os.environ.get("ONELINE_TOP_K", "5"))
RETRIEVER_MIN_RELEVANCE = 0.5

# Selector
FUNCTIONALITY_GATE = 0.9
WEIGHTS = {"functionality": 0.40, "ux_clarity": 0.35, "design_coherence": 0.25}

# Concurrency. Three candidates build and are judged at once, one thread each.
MAX_PARALLEL_BUILDS = int(os.environ.get("ONELINE_MAX_PARALLEL", "3"))

# Always-on mobile tags that apply to nearly every personal tool.
ALWAYS_ON_TAGS = [
    "mobile_first",
    "touch_targets",
    "primary_cta",
    "thumb_zone",
    "single_screen",
]


def gemini_api_key() -> "str | None":
    """Read the Gemini API key from the environment. Never hardcode or log it."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
