"""Design coherence judge, gemini-3.5-flash, thinking medium.

Scores conformance to the shared design system, not taste. Five sub-scores:
token_conformance, hero_discipline, typography_consistency, spatial_consistency,
restraint. The prompt embeds the six approved accent hexes and the base token
hexes so a second accent or an off-system color is caught and penalized.

The headline is computed from the sub-scores minus a per-violation penalty, so
system violations bite even if the model under-scores a sub-score. With no
violations the headline equals the mean of the sub-scores, matching the contract
example.
"""
from __future__ import annotations

from typing import Callable

from .config import MAX_HTML_CHARS
from .prompts import DESIGN_COHERENCE_SYSTEM
from .sanitize import as_str, as_str_list, mean, no_em_dashes, unit

_SUB_KEYS = [
    "token_conformance",
    "hero_discipline",
    "typography_consistency",
    "spatial_consistency",
    "restraint",
]

# Each named system violation pulls the headline down on top of the model's
# sub-scores, so off-system colors and second accents are penalized heavily.
VIOLATION_PENALTY = 0.1


def build_user_payload(candidate: dict, plan: dict) -> str:
    html = candidate.get("html") or ""
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS]
    declared_accent = candidate.get("accent")
    lines = [
        "Tool category: " + as_str(plan.get("tool_category")),
    ]
    if declared_accent:
        lines.append(
            "Declared accent: " + as_str(declared_accent)
            + " (must be one of the six approved hexes and the only accent used)"
        )
    lines += ["", "Candidate HTML:", html]
    return "\n".join(lines)


def _normalize(raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    sub_in = raw.get("sub_scores") if isinstance(raw.get("sub_scores"), dict) else {}
    sub_scores = {key: unit(sub_in.get(key)) for key in _SUB_KEYS}
    violations = as_str_list(raw.get("system_violations"))
    headline = unit(mean(list(sub_scores.values())) - VIOLATION_PENALTY * len(violations))
    detail = {
        "design_coherence_score": headline,
        "sub_scores": sub_scores,
        "system_violations": violations,
        "reasoning": as_str(raw.get("reasoning")),
    }
    return no_em_dashes(detail)


def score_design_coherence(
    candidate: dict,
    plan: dict,
    generate: Callable[[str, str, str], dict],
    thinking: str = "medium",
) -> dict:
    """Return the design_coherence detail object matching the JudgeScores shape."""
    user = build_user_payload(candidate, plan)
    try:
        raw = generate(DESIGN_COHERENCE_SYSTEM, user, thinking)
    except Exception:
        raw = {}
    return _normalize(raw)
