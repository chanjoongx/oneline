"""Phase 1 stubs so the orchestration loop runs end to end before sandbox/,
judges/, and web/ deliver their real implementations. Each stub satisfies the
matching Protocol in interfaces.py and emits shapes that pass the shared schemas.

These are for local testing and the early skeleton only. The real implementations
are injected via orchestrator.Deps. No em dashes in any emitted string or HTML.
"""
from __future__ import annotations

import time
from typing import Optional


def _tool_html(brief: str, accent: str) -> str:
    """A minimal valid tool: dark base, one accent, one hero, one bottom action."""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Oneline tool</title>\n"
        "<style>\n"
        ":root{--bg:#0A0A0B;--surface:#141416;--border:#2A2A2E;--text:#F5F5F7;"
        "--text-muted:#9A9AA2;--accent:" + accent + ";--accent-ink:#0A0A0B;--radius:12px}\n"
        "*{box-sizing:border-box}\n"
        "body{margin:0;min-height:100dvh;max-width:480px;margin:0 auto;background:var(--bg);"
        "color:var(--text);font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;"
        "display:flex;flex-direction:column;align-items:center;justify-content:space-between;padding:24px}\n"
        ".title{font-size:24px;font-weight:600;margin:0}\n"
        ".hero{font-family:ui-monospace,monospace;font-size:48px;font-weight:700;text-align:center}\n"
        ".btn{width:100%;min-height:52px;border:0;border-radius:var(--radius);background:var(--accent);"
        "color:var(--accent-ink);font-size:16px;font-weight:600}\n"
        "</style></head>\n"
        "<body>\n"
        '<h1 class="title">Oneline</h1>\n'
        '<div class="hero" id="value">0</div>\n'
        '<button class="btn" onclick="var v=document.getElementById(\'value\');'
        "v.textContent=(+v.textContent+1)\">Add one</button>\n"
        "</body></html>\n"
    )


class StubImplementer:
    """Returns a tiny valid candidate per strategy."""

    _ACCENTS = {"A": "#5B8DEF", "B": "#3FB950", "C": "#A371F7"}

    def build_candidate(self, strategy: dict, brief: str, lessons: list) -> dict:
        cid = strategy["id"]
        accent = self._ACCENTS.get(cid, "#5B8DEF")
        return {
            "candidate_id": cid,
            "html": _tool_html(brief, accent),
            "environment_id": f"stub-env-{cid}-{int(time.time())}",
            "steps": 1,
            "rationale": (
                f"Rationale: stub candidate {cid}, placeholder accent, single hero "
                "with one full-width action in the thumb zone."
            ),
            "accent": accent,
            "framework": strategy.get("framework"),
            "ux_emphasis": strategy.get("ux_emphasis"),
        }


class StubJudge:
    """Deterministic scores. B is strongest so a winner emerges clearly."""

    _SCORES = {
        "A": (1.0, 0.82, 0.78),
        "B": (1.0, 0.92, 0.88),
        "C": (1.0, 0.85, 0.90),
    }

    def judge(self, candidate: dict, plan: dict) -> dict:
        cid = candidate["candidate_id"]
        f, u, d = self._SCORES.get(cid, (1.0, 0.80, 0.80))
        return {
            "candidate_id": cid,
            "functionality_score": f,
            "ux_clarity_score": u,
            "design_coherence_score": d,
            "functionality": {
                "functionality_score": f,
                "passed": ["loads_under_3s", "primary_action_works"],
                "failed": [],
                "screenshot": None,
            },
            "ux_clarity": {
                "ux_clarity_score": u,
                "sub_scores": {
                    "primary_action_dominance": u,
                    "thumb_reach": 1.0,
                    "touch_target_size": 1.0,
                    "visual_simplicity": u,
                    "feedback_states": u,
                    "concrete_language": 1.0,
                },
                "production_app_smells": [],
                "reasoning": "stub score",
                "improvement_suggestions": [],
            },
            "design_coherence": {
                "design_coherence_score": d,
                "sub_scores": {
                    "token_conformance": d,
                    "hero_discipline": 1.0,
                    "typography_consistency": d,
                    "spatial_consistency": d,
                    "restraint": d,
                },
                "system_violations": [],
                "reasoning": "stub score",
            },
        }


class StubDeployer:
    """Returns a fake but well-formed deployment record."""

    def deploy(self, winner_html: str) -> dict:
        ts = int(time.time())
        return {
            "url": f"https://oneline-demo-1.example.run.app/tools/tool-{ts}.html",
            "service": "oneline-demo-1",
            "ts": ts,
        }


class StubCurator:
    """Emits a generalizable lesson for clearly weaker losers, else None."""

    def curate(self, loser: dict, plan: dict) -> Optional[dict]:
        if loser.get("ux_clarity_score", 1.0) >= 0.90:
            return None
        category = plan.get("tool_category", "utility")
        return {
            "tool_category": category,
            "lesson_class": "ux_clarity",
            "ux_anti_pattern": "ambiguous_cta",
            "tags": ["mobile_first", "primary_cta", "thumb_zone", category],
            "lesson_text": (
                "Name the primary action with a verb and a noun so the next tap is "
                "obvious without reading anything else."
            ),
            "bad_pattern": "a generic primary button labeled Go or Submit",
            "good_pattern": "a verb plus noun primary button in the thumb zone",
            "severity": "medium",
            "score_delta": -0.1,
        }
