"""The Retriever. Tag-based relevance over knowledge_base.json, returns the
top-K lessons for a plan.

The default path is deterministic (no model call): stable on a tiny knowledge
base, fast, and demo-safe. A gemini-3.5-flash path (thinking low) is provided to
match the shared retriever contract and can be swapped in. Both return the same
RetrievedLessons shape.

Relevance combines three signals, each stable regardless of corpus size:
- category match: the lesson is for this tool category, or the category is a tag
- broad applicability: the anti-pattern applies to nearly every mobile tool
- tag and term overlap between the plan and the lesson
"""
from __future__ import annotations

import json
import re

from . import prompts, schemas
from .config import (
    ALWAYS_ON_TAGS,
    RETRIEVER_MIN_RELEVANCE,
    RETRIEVER_TOP_K,
)
from .gemini import generate_json

# Anti-patterns that apply to nearly every personal tool, per the retriever spec:
# primary action placement, touch target size, feedback states, button text.
BROAD_ANTI_PATTERNS = {
    "buried_primary_action",
    "tiny_touch_targets",
    "ambiguous_cta",
    "missing_feedback_state",
    "generic_button_text",
    "thumb_unreachable",
}

_WORD = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> set:
    return set(_WORD.findall((text or "").lower()))


def _query_terms(plan: dict) -> set:
    terms = set(ALWAYS_ON_TAGS)
    terms.add((plan.get("tool_category") or "").lower())
    for interaction in plan.get("core_interactions", []):
        terms |= _tokens(interaction)
    terms.discard("")
    return terms


def _relevance(plan: dict, lesson: dict) -> float:
    query = _query_terms(plan)
    lesson_tags = {t.lower() for t in lesson.get("tags", [])}
    lesson_terms = lesson_tags | _tokens(lesson.get("lesson_text", ""))

    category = (plan.get("tool_category") or "").lower()
    is_category = 1.0 if (lesson.get("tool_category") == plan.get("tool_category")
                          or category in lesson_tags) else 0.0
    is_broad = 1.0 if lesson.get("ux_anti_pattern") in BROAD_ANTI_PATTERNS else 0.0
    tag_ratio = (len(query & lesson_tags) / len(lesson_tags)) if lesson_tags else 0.0

    union = query | lesson_terms
    jaccard = (len(query & lesson_terms) / len(union)) if union else 0.0

    base = max(0.60 * is_category, 0.55 * is_broad, 0.50 * tag_ratio)
    return round(min(1.0, base + 0.30 * jaccard), 3)


def retrieve(
    plan: dict,
    lessons: list,
    k: int = RETRIEVER_TOP_K,
    validate: bool = True,
) -> dict:
    """Deterministic tag-based retrieval. Returns a RetrievedLessons dict."""
    scored = []
    for lesson in lessons:
        relevance = _relevance(plan, lesson)
        if relevance >= RETRIEVER_MIN_RELEVANCE:
            scored.append((relevance, lesson))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    out = {
        "retrieved_lessons": [
            {
                "id": lesson["id"],
                "lesson_text": lesson["lesson_text"],
                "good_pattern": lesson["good_pattern"],
                "relevance_score": relevance,
            }
            for relevance, lesson in scored[:k]
        ]
    }
    if validate:
        schemas.validate(out, "retrieved_lessons")
    return out


def gemini_retrieve(
    plan: dict,
    lessons: list,
    k: int = RETRIEVER_TOP_K,
    client=None,
    validate: bool = True,
) -> dict:
    """Spec path: gemini-3.5-flash, thinking low, scores lesson relevance."""
    system = prompts.compose(prompts.RETRIEVER_SYSTEM)
    user = json.dumps({"plan": plan, "knowledge_base": {"lessons": lessons}})
    out = generate_json(system, user, thinking="low", temperature=0.2, client=client)
    items = [
        x
        for x in out.get("retrieved_lessons", [])
        if x.get("relevance_score", 0) >= RETRIEVER_MIN_RELEVANCE
    ]
    items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    out = {"retrieved_lessons": items[:k]}
    if validate:
        schemas.validate(out, "retrieved_lessons")
    return out
