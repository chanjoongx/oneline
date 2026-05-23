"""UX clarity judge, gemini-3.5-flash, thinking high.

The grandmother test: can a 70-year-old find and use the primary action within
30 seconds with no instruction. Six sub-scores, minus 0.1 for each production-app
smell. The headline is computed from the sub-scores and the smells so the rubric
math is reproducible and never drifts on the model's own arithmetic.
"""
from __future__ import annotations

from typing import Callable

from .config import MAX_HTML_CHARS
from .prompts import UX_CLARITY_SYSTEM
from .sanitize import as_str, as_str_list, mean, no_em_dashes, unit

_SUB_KEYS = [
    "primary_action_dominance",
    "thumb_reach",
    "touch_target_size",
    "visual_simplicity",
    "feedback_states",
    "concrete_language",
]

# The production-app smells that subtract from the score, per the UX clarity rubric.
SMELL_PENALTY = 0.1


def build_user_payload(candidate: dict, plan: dict) -> str:
    html = candidate.get("html") or ""
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS]
    lines = [
        "Tool category: " + as_str(plan.get("tool_category")),
        "Core interactions: " + as_str(plan.get("core_interactions")),
        "Success criteria: " + as_str(plan.get("success_criteria")),
        "",
        "Candidate HTML:",
        html,
    ]
    return "\n".join(lines)


def _normalize(raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    sub_in = raw.get("sub_scores") if isinstance(raw.get("sub_scores"), dict) else {}
    sub_scores = {key: unit(sub_in.get(key)) for key in _SUB_KEYS}
    smells = as_str_list(raw.get("production_app_smells"))
    headline = unit(mean(list(sub_scores.values())) - SMELL_PENALTY * len(smells))
    detail = {
        "ux_clarity_score": headline,
        "sub_scores": sub_scores,
        "production_app_smells": smells,
        "reasoning": as_str(raw.get("reasoning")),
        "improvement_suggestions": as_str_list(raw.get("improvement_suggestions")),
    }
    return no_em_dashes(detail)


def score_ux_clarity(
    candidate: dict,
    plan: dict,
    generate: Callable[[str, str, str], dict],
    thinking: str = "high",
) -> dict:
    """Return the ux_clarity detail object matching the shared JudgeScores shape."""
    user = build_user_payload(candidate, plan)
    try:
        raw = generate(UX_CLARITY_SYSTEM, user, thinking)
    except Exception:
        raw = {}
    return _normalize(raw)
