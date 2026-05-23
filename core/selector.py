"""The Selector. Deterministic, functionality-gated, weighted.

A broken tool is useless even for one person, so functionality gates first.
Among qualifiers, final = 0.40 functionality + 0.35 ux_clarity + 0.25 design.
Tie-break on ux_clarity.
"""
from __future__ import annotations

from . import schemas
from .config import FUNCTIONALITY_GATE, WEIGHTS


def merge_scores(candidate: dict, judge_scores: dict) -> dict:
    """Combine a Candidate with its headline judge scores into a scored candidate."""
    scored = dict(candidate)
    scored["functionality_score"] = judge_scores["functionality_score"]
    scored["ux_clarity_score"] = judge_scores["ux_clarity_score"]
    scored["design_coherence_score"] = judge_scores["design_coherence_score"]
    return scored


def final_score(candidate: dict) -> float:
    return round(
        WEIGHTS["functionality"] * candidate["functionality_score"]
        + WEIGHTS["ux_clarity"] * candidate["ux_clarity_score"]
        + WEIGHTS["design_coherence"] * candidate["design_coherence_score"],
        4,
    )


def select_winner(
    candidates: list,
    gate: float = FUNCTIONALITY_GATE,
    validate: bool = True,
) -> dict:
    """Pick the winner from scored candidates. Returns a Selection dict.

    Each candidate must carry candidate_id and the three headline scores
    (functionality_score, ux_clarity_score, design_coherence_score).
    """
    qualifying = [c for c in candidates if c.get("functionality_score", 0) >= gate]
    if not qualifying:
        result = {
            "winner": None,
            "reason": (
                "All candidates failed the functionality gate. "
                "Try a simpler version of the request."
            ),
        }
        if validate:
            schemas.validate(result, "selection")
        return result

    for candidate in qualifying:
        candidate["final_score"] = final_score(candidate)

    winner = max(qualifying, key=lambda c: (c["final_score"], c["ux_clarity_score"]))
    losers = [c for c in candidates if c.get("candidate_id") != winner.get("candidate_id")]
    result = {
        "winner": winner,
        "losers": losers,
        "rationale": f"Selected {winner['candidate_id']} at {winner['final_score']:.2f}",
    }
    if validate:
        schemas.validate(result, "selection")
    return result
