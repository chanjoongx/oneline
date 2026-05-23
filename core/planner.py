"""The Planner agent. gemini-3.5-flash, thinking high.

Takes a plain-language need, returns a Plan: scope decision, tool category, core
interactions, data model, success criteria, and three candidate strategies.

core_interactions and success_criteria describe behavior only. Visual styling
(color, the single accent, dark base, typography, layout) is left entirely to the
shared design system, so the plan never requests colors or theming. A behavior
plus design split keeps candidates on-system and protects design coherence.

Plans are minimal. Oneline tools serve one person and are thrown away tomorrow,
so the plan scopes only the literal request and never bolts on extras the user
did not ask for (saved history, timestamps, rounding modes, clear-all, export,
sharing, settings). Smaller plans yield smaller, complete tools that build inside
the sandbox without truncation.
"""
from __future__ import annotations

import re

from . import prompts, schemas
from .gemini import generate_json

TOOL_CATEGORIES = {
    "timer", "tracker", "calculator", "flashcards", "checklist", "decision_tool",
    "quiz", "single_user_game", "log", "converter", "randomizer", "planner",
    "display_only", "utility",
}

# The three candidate strategies are fixed archetypes from the design system.
# The model supplies the substance (category, interactions, data, criteria); the
# build variants stay constant so candidates remain diverse and on-system, and a
# chatty live model cannot break the contract by rewriting ux_emphasis or
# framework into a free-text description.
_CANONICAL_STRATEGIES = [
    {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
    {"id": "B", "framework": "tailwind_cdn", "ux_emphasis": "polish"},
    {"id": "C", "framework": "tailwind_cdn", "ux_emphasis": "minimal_whitespace"},
]

# Visual styling belongs to the design system, never the plan. These detect a
# core_interaction or success_criterion that requests colors, a background or
# screen color change, color-coded states, or multi-color theming, which make
# implementers break the one-accent dark base and tank design coherence.
_VISUAL_PATTERNS = re.compile(
    r"\bcolou?r"
    r"|\bgradient\b|\brainbow\b|\bpalette\b|\bhue\b|\btheming\b|\bthemed\b"
    r"|\bdark mode\b|\blight mode\b"
    r"|\b(?:background|screen|page|backdrop)\b[\w\s]{0,30}"
    r"\b(?:change|changes|shift|shifts|turn|turns|flash|flashes|fill|fills|theme|glow|colou?r)\b",
    re.IGNORECASE,
)
_NAMED_COLOR = re.compile(
    r"\b(red|green|blue|amber|yellow|orange|purple|violet|teal|pink|cyan|magenta|crimson|scarlet|indigo)\b",
    re.IGNORECASE,
)
_GENERIC_INTERACTION = "Use the tool's primary action."
_GENERIC_CRITERION = "The tool performs its core function reliably."


def _is_visual_styling(text: str) -> bool:
    """True when the text requests appearance the design system owns."""
    if not text:
        return False
    if _VISUAL_PATTERNS.search(text):
        return True
    # Two or more distinct named colors is multi-color theming, for example
    # "red for work and green for rest". One stray color word (orange juice) is
    # left alone to avoid false positives.
    distinct = {match.lower() for match in _NAMED_COLOR.findall(text)}
    return len(distinct) >= 2


# Features the planner tends to bolt onto a simple request. An item that asks for
# one is dropped unless the need explicitly asks for it, so "software for one,
# throw away tomorrow" stays minimal and the generated HTML stays small enough to
# build completely. Categories that are inherently stateful keep their persistence.
_MAX_ITEMS = 3
_STATEFUL_CATEGORIES = {
    "tracker", "log", "checklist", "flashcards", "quiz", "single_user_game",
}
_SCOPE_CREEP = {
    "history": re.compile(
        r"\bhistory\b"
        r"|\bsaved?\b[\w\s]{0,15}\b(?:calculation|result|entry|entries|split|session|value)s?\b"
        r"|\b(?:past|previous|recent)\b[\w\s]{0,15}\b(?:calculation|result|entry|entries|session)s?\b"
        r"|\blog of\b",
        re.IGNORECASE,
    ),
    "timestamp": re.compile(
        r"\btimestamps?\b|\bdate and time\b|\bwith a timestamp\b|\blogged at\b",
        re.IGNORECASE,
    ),
    "rounding": re.compile(
        r"\brounding\b|\bround\b[\w\s]{0,15}\b(?:up|down|nearest)\b|\bround up\b|\bround down\b",
        re.IGNORECASE,
    ),
    "clear_all": re.compile(
        r"\bclear(?:ed|s)?\b[\w\s]{0,10}\ball\b|\bdelete all\b|\bremove all\b|\breset all\b"
        r"|\bclear (?:the )?history\b|\bclear-all\b",
        re.IGNORECASE,
    ),
    "export": re.compile(r"\bexport\b|\bdownload\b|\bshare\b|\bsharing\b", re.IGNORECASE),
}
_NEED_ALLOW = {
    "history": re.compile(r"\bhistor|\bsave|\blog\b|\btrack|\brecord|\bremember|\bkeep\b", re.IGNORECASE),
    "timestamp": re.compile(r"\btimestamp|\bdate\b|\bwhen\b", re.IGNORECASE),
    "rounding": re.compile(r"\bround", re.IGNORECASE),
    "clear_all": re.compile(r"\bclear|\bdelete|\bremove|\breset", re.IGNORECASE),
    "export": re.compile(r"\bexport|\bdownload|\bshare", re.IGNORECASE),
}


def _is_scope_creep(text: str, need: str, category: str) -> bool:
    """True when the text adds a feature the literal need did not ask for."""
    if category in _STATEFUL_CATEGORIES:
        # Persistence and history are the point of these tools; do not strip.
        return False
    for feature, pattern in _SCOPE_CREEP.items():
        if pattern.search(text) and not _NEED_ALLOW[feature].search(need or ""):
            return True
    return False


def _minimal(items: list, need: str, category: str, fallback: str) -> list:
    """Keep a few minimal behavioral items: drop visual styling and unrequested
    features, cap the count, and never return an empty required array."""
    kept = [
        item
        for item in items
        if isinstance(item, str)
        and item.strip()
        and not _is_visual_styling(item)
        and not _is_scope_creep(item, need, category)
    ]
    return (kept or [fallback])[:_MAX_ITEMS]


class PlanError(RuntimeError):
    """Raised when the planner cannot produce a valid Plan."""


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _normalize(plan: dict, need: str = "") -> dict:
    """Make the plan schema-valid, behavioral, and minimal.

    Fills the nullable and list fields, coerces tool_category to a known category,
    strips visual styling and unrequested scope-creep features, caps each list to
    a few minimal items, and forces the three fixed strategy archetypes so a
    chatty live model cannot break the contract.
    """
    plan.setdefault("rejected", False)
    plan.setdefault("rejection_reason", None)
    plan.setdefault("suggested_alternative", None)
    if plan.get("tool_category") not in TOOL_CATEGORIES:
        plan["tool_category"] = "utility"
    category = plan["tool_category"]
    plan["core_interactions"] = _minimal(
        _as_list(plan.get("core_interactions")), need, category, _GENERIC_INTERACTION
    )
    plan["success_criteria"] = _minimal(
        _as_list(plan.get("success_criteria")), need, category, _GENERIC_CRITERION
    )
    plan.setdefault("data_model", "")
    plan["candidate_strategies"] = [dict(s) for s in _CANONICAL_STRATEGIES]
    return plan


def plan(need: str, client=None, validate: bool = True) -> dict:
    """Run the Planner on a plain-language need and return a Plan dict."""
    if not need or not need.strip():
        raise PlanError("empty request")
    system = prompts.compose(prompts.PLANNER_SYSTEM)
    out = generate_json(system, need.strip(), thinking="high", temperature=0.5, client=client)
    if not isinstance(out, dict):
        raise PlanError("planner did not return a JSON object")
    out = _normalize(out, need)
    if validate:
        try:
            schemas.validate(out, "plan")
        except Exception as exc:  # surface a clear, actionable error
            raise PlanError(f"planner output failed schema validation: {exc}") from exc
    return out
