"""Curator, gemini-3.5-flash, thinking high.

Implements the Curator Protocol from core/interfaces.py:
    curate(loser, plan) -> curator_output | None

It turns each losing candidate into one universal, reusable UX lesson that
matches the curator_output subset of shared/schemas/lesson.schema.json. Lessons
too specific to one request are skipped (the curator returns None). Every emitted
lesson uses the shared tag vocabulary so the tag based retriever can find it, and
the core write helper later enriches it into a stored Lesson with id, created_at,
applied_count, and prevented_repeats.

No em dashes in any field.
"""
from __future__ import annotations

from typing import Callable, Optional

from .config import MAX_HTML_CHARS
from .prompts import CURATOR_SYSTEM
from .sanitize import as_str, as_str_list, no_em_dashes
from .schema_check import (
    ALWAYS_ON_TAGS,
    ANTI_PATTERNS,
    LESSON_CLASSES,
    SEVERITIES,
    TOOL_CATEGORIES,
    is_valid_curator_output,
)

GenerateFn = Callable[[str, str, str], dict]

# Fallback anti-pattern per lesson class, used only when the model returns an
# off-vocabulary anti-pattern that cannot be mapped to a known one.
_DEFAULT_ANTI = {
    "ux_clarity": "ambiguous_cta",
    "design_coherence": "palette_drift",
    "functionality": "missing_feedback_state",
}


def build_user_payload(loser: dict, plan: dict) -> str:
    html = loser.get("html") or ""
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS]
    lines = [
        "Tool category: " + as_str(plan.get("tool_category")),
        "Core interactions: " + as_str(plan.get("core_interactions")),
        "Success criteria: " + as_str(plan.get("success_criteria")),
        "",
        "Losing candidate id: " + as_str(loser.get("candidate_id")),
        "Functionality score: " + as_str(loser.get("functionality_score")),
        "UX clarity score: " + as_str(loser.get("ux_clarity_score")),
        "Design coherence score: " + as_str(loser.get("design_coherence_score")),
    ]
    # Judge detail may ride along on the loser; use it when present.
    ux = loser.get("ux_clarity") if isinstance(loser.get("ux_clarity"), dict) else {}
    design = (
        loser.get("design_coherence")
        if isinstance(loser.get("design_coherence"), dict)
        else {}
    )
    if ux.get("reasoning"):
        lines.append("UX reasoning: " + as_str(ux.get("reasoning")))
    if ux.get("production_app_smells"):
        lines.append("Production app smells: " + as_str(ux.get("production_app_smells")))
    if design.get("reasoning"):
        lines.append("Design reasoning: " + as_str(design.get("reasoning")))
    if design.get("system_violations"):
        lines.append("System violations: " + as_str(design.get("system_violations")))
    if loser.get("rationale"):
        lines.append("Implementer rationale: " + as_str(loser.get("rationale")))
    lines += ["", "Losing candidate HTML:", html]
    return "\n".join(lines)


def _coerce_enum(value, allowed, default):
    text = as_str(value).strip().lower()
    if text in allowed:
        return text
    for option in allowed:
        if option in text or text in option:
            return option
    return default


def _coerce_score_delta(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return -0.2
    if number > 0:
        number = -number
    if number < -1:
        return -1.0
    if number > 0:
        return 0.0
    return round(number, 4)


def _coerce_tags(value, tool_category: str) -> list:
    tags = [tag.strip().lower().replace(" ", "_") for tag in as_str_list(value)]
    tags = [tag for tag in tags if tag]
    # Always carry the tool category and at least one always-on tag so the tag
    # based retriever can match this lesson.
    if tool_category not in tags:
        tags.append(tool_category)
    if not any(tag in ALWAYS_ON_TAGS for tag in tags):
        tags.append("mobile_first")
    # Dedupe, preserve order.
    seen = set()
    deduped = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def normalize_curator_output(raw, plan: dict) -> Optional[dict]:
    """Coerce a model response into a valid curator_output, or None to skip."""
    if not isinstance(raw, dict):
        return None
    # The model returns null when nothing generalizable was found.
    if not raw.get("lesson_text") and not raw.get("ux_anti_pattern"):
        return None

    plan_category = as_str(plan.get("tool_category")).strip().lower()
    default_category = plan_category if plan_category in TOOL_CATEGORIES else "utility"
    tool_category = _coerce_enum(raw.get("tool_category"), TOOL_CATEGORIES, default_category)
    lesson_class = _coerce_enum(raw.get("lesson_class"), LESSON_CLASSES, "ux_clarity")
    anti_pattern = _coerce_enum(
        raw.get("ux_anti_pattern"), ANTI_PATTERNS, _DEFAULT_ANTI[lesson_class]
    )
    lesson_text = as_str(raw.get("lesson_text")).strip()
    if not lesson_text:
        return None

    out = {
        "tool_category": tool_category,
        "lesson_class": lesson_class,
        "ux_anti_pattern": anti_pattern,
        "tags": _coerce_tags(raw.get("tags"), tool_category),
        "lesson_text": lesson_text,
        "bad_pattern": as_str(raw.get("bad_pattern")).strip(),
        "good_pattern": as_str(raw.get("good_pattern")).strip(),
        "severity": _coerce_enum(raw.get("severity"), SEVERITIES, "medium"),
        "score_delta": _coerce_score_delta(raw.get("score_delta")),
    }
    return no_em_dashes(out)


class OnelineCurator:
    """Turns a loser into a reusable lesson, or None when nothing generalizes."""

    def __init__(self, generate: Optional[GenerateFn] = None, thinking: str = "high"):
        self._generate = generate
        self.thinking = thinking

    def _gen(self, system: str, user: str, thinking: str) -> dict:
        if self._generate is not None:
            return self._generate(system, user, thinking)
        from .gemini_client import generate_json

        return generate_json(system, user, thinking)

    def curate(self, loser: dict, plan: dict) -> Optional[dict]:
        user = build_user_payload(loser, plan)
        try:
            raw = self._gen(CURATOR_SYSTEM, user, self.thinking)
        except Exception:
            return None
        out = normalize_curator_output(raw, plan)
        if out is None:
            return None
        # Final guard against the shared contract. A lesson that does not match
        # the curator_output subset is dropped rather than poisoning the kb.
        if not is_valid_curator_output(out):
            return None
        return out
