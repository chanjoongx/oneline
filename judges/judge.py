"""OnelineJudge, the three-layer judge for one candidate.

Implements the JudgeClient Protocol from core/interfaces.py:
    judge(candidate, plan) -> JudgeScores

It runs the deterministic functionality judge (Playwright in the candidate's own
managed sandbox, reusing environment_id), the UX clarity judge (gemini-3.5-flash
thinking high), and the design coherence judge (gemini-3.5-flash thinking
medium), then assembles one JudgeScores object that matches
shared/schemas/judge_scores.schema.json: three headline numbers the selector
reads, plus the three detail objects for the dashboard and the curator.

All model based judges and the curator use gemini-3.5-flash, no other model. No
em dashes in any emitted field.
"""
from __future__ import annotations

from typing import Callable, Optional

from .design_coherence import score_design_coherence
from .functionality import FunctionalityJudge
from .sanitize import no_em_dashes, unit
from .ux_clarity import score_ux_clarity

GenerateFn = Callable[[str, str, str], dict]


def assemble_judge_scores(
    candidate_id: str,
    functionality_detail: dict,
    ux_detail: dict,
    design_detail: dict,
) -> dict:
    """Combine the three detail objects into one JudgeScores object.

    The headline numbers are taken straight from the detail objects so the
    top-level scores the selector reads and the detail the dashboard reads never
    disagree.
    """
    functionality_score = unit(functionality_detail.get("functionality_score"))
    ux_score = unit(ux_detail.get("ux_clarity_score"))
    design_score = unit(design_detail.get("design_coherence_score"))

    # Keep the detail headline equal to the top-level headline.
    functionality_detail = dict(functionality_detail)
    functionality_detail["functionality_score"] = functionality_score
    ux_detail = dict(ux_detail)
    ux_detail["ux_clarity_score"] = ux_score
    design_detail = dict(design_detail)
    design_detail["design_coherence_score"] = design_score

    scores = {
        "candidate_id": candidate_id,
        "functionality_score": functionality_score,
        "ux_clarity_score": ux_score,
        "design_coherence_score": design_score,
        "functionality": functionality_detail,
        "ux_clarity": ux_detail,
        "design_coherence": design_detail,
    }
    return no_em_dashes(scores)


class OnelineJudge:
    """The three-layer judge. Inject a functionality judge and a generate fn.

    functionality defaults to FunctionalityJudge, which reuses the candidate's
    environment_id for a real sandbox run and returns pass for stub environments
    so the loop runs end to end before sandboxes are wired. generate defaults to
    the gemini-3.5-flash JSON call; the offline tests inject a fake in its place.
    """

    def __init__(
        self,
        functionality=None,
        generate: Optional[GenerateFn] = None,
        ux_thinking: str = "high",
        design_thinking: str = "medium",
    ):
        self.functionality = functionality if functionality is not None else FunctionalityJudge()
        self._generate = generate
        self.ux_thinking = ux_thinking
        self.design_thinking = design_thinking

    def _gen(self, system: str, user: str, thinking: str) -> dict:
        if self._generate is not None:
            return self._generate(system, user, thinking)
        from .gemini_client import generate_json

        return generate_json(system, user, thinking)

    def judge(self, candidate: dict, plan: dict) -> dict:
        """Score one candidate on all three axes. Returns a JudgeScores dict."""
        candidate_id = candidate.get("candidate_id")
        functionality_detail = self.functionality.score(candidate, plan)
        ux_detail = score_ux_clarity(candidate, plan, self._gen, self.ux_thinking)
        design_detail = score_design_coherence(
            candidate, plan, self._gen, self.design_thinking
        )
        return assemble_judge_scores(
            candidate_id, functionality_detail, ux_detail, design_detail
        )
