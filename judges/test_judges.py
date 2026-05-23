"""Offline self-check for the judges. No network, no API key.

Run directly:   python judges/test_judges.py
Or with pytest: pytest judges/test_judges.py

Every model call is faked so the suite is fully offline. The fake stands in for
the gemini-3.5-flash JSON call and lets us assert the JudgeScores shape, the
headline math, the long dash hygiene, and the curator contract.
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace

# Allow running as a plain script by putting the repo root on the path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from judges import (  # noqa: E402
    FunctionalityJudge,
    ManagedAgentsRunner,
    OnelineCurator,
    OnelineJudge,
    StubFunctionalityJudge,
    build_run_prompt,
    default_curator,
    default_judge,
    generate_playwright_test,
    live_judge,
)
from judges.functionality import (  # noqa: E402
    FunctionalityInfraError,
    SandboxFunctionalityJudge,
    build_checks,
)
from judges.schema_check import is_valid_curator_output, validate_judge_scores  # noqa: E402

SAMPLE_PLAN = {
    "rejected": False,
    "rejection_reason": None,
    "suggested_alternative": None,
    "tool_category": "tracker",
    "core_interactions": ["Increment the count", "Reset the count at midnight"],
    "data_model": "count and last-reset date in localStorage",
    "success_criteria": [
        "Tapping the button increases the count",
        "Count persists on reload",
    ],
    "candidate_strategies": [
        {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
    ],
}

GOOD_HTML = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width, initial-scale=1'>"
    "<style>:root{--bg:#0A0A0B;--text:#F5F5F7;--accent:#3FB950;--accent-ink:#0A0A0B}"
    "body{background:var(--bg);color:var(--text)}"
    ".hero{font-family:ui-monospace;font-size:48px;font-weight:700;text-align:center}"
    ".btn{height:52px;background:var(--accent);color:var(--accent-ink)}</style></head>"
    "<body><div class=hero id=v>0</div>"
    "<button class=btn onclick=\"v.textContent=(+v.textContent+1)\">Add one</button>"
    "</body></html>"
)

GOOD_CANDIDATE = {
    "candidate_id": "A",
    "html": GOOD_HTML,
    "environment_id": "stub-env-A-123",
    "accent": "#3FB950",
}


# A long dash built at runtime so this source file stays free of literal em
# dashes while still exercising the sanitizer that must strip them.
EM = chr(0x2014)


def fake_generate(system: str, user: str, thinking: str) -> dict:
    """Stand in for gemini-3.5-flash. Returns canned JSON per judge, including a
    long dash to prove the sanitizer strips it."""
    if "UX Clarity Judge" in system:
        assert thinking == "high"
        return {
            "ux_clarity_score": 0.99,
            "sub_scores": {
                "primary_action_dominance": 1.0,
                "thumb_reach": 1.0,
                "touch_target_size": 1.0,
                "visual_simplicity": 0.8,
                "feedback_states": 0.9,
                "concrete_language": 1.0,
            },
            "production_app_smells": [],
            "reasoning": "Add one is the dominant action in the thumb zone " + EM + " clear.",
            "improvement_suggestions": ["Flash on tap"],
        }
    if "Design Coherence Judge" in system:
        assert thinking == "medium"
        # Confirm the six approved accent hexes are in the prompt.
        for hex_value in ("#5B8DEF", "#3FB950", "#E3A008", "#A371F7", "#F85149", "#2DD4BF"):
            assert hex_value in system
        return {
            "design_coherence_score": 0.9,
            "sub_scores": {
                "token_conformance": 1.0,
                "hero_discipline": 1.0,
                "typography_consistency": 0.9,
                "spatial_consistency": 0.8,
                "restraint": 0.7,
            },
            "system_violations": [],
            "reasoning": "Single green accent, one mono hero, 8px grid.",
        }
    if "Curator" in system:
        assert thinking == "high"
        return {
            "tool_category": "tracker",
            "lesson_class": "ux_clarity",
            "ux_anti_pattern": "generic_button_text",
            "tags": ["tracker", "primary_cta"],
            "lesson_text": "Name the primary action with a verb and a noun " + EM + " not Go.",
            "bad_pattern": "a button labeled Go",
            "good_pattern": "a verb plus noun button like Add one",
            "severity": "medium",
            "score_delta": -0.2,
        }
    raise AssertionError("unexpected system prompt")


def off_system_design_generate(system: str, user: str, thinking: str) -> dict:
    if "Design Coherence Judge" in system:
        return {
            "design_coherence_score": 0.9,
            "sub_scores": {
                "token_conformance": 0.2,
                "hero_discipline": 1.0,
                "typography_consistency": 0.9,
                "spatial_consistency": 0.8,
                "restraint": 0.4,
            },
            "system_violations": [
                "second accent #FF00AA used on a card",
                "purple to pink decorative gradient",
            ],
            "reasoning": "Off-system magenta accent and a decorative gradient.",
        }
    return fake_generate(system, user, thinking)


def test_playwright_test_generates_valid_python():
    script = generate_playwright_test(
        SAMPLE_PLAN["success_criteria"], SAMPLE_PLAN["core_interactions"], GOOD_HTML
    )
    compile(script, "<generated-test>", "exec")
    assert "ONELINE_RESULT" in script
    # Loads the tool from the known path in the sandbox.
    assert 'URL = "file:///work/tool.html"' in script
    # Writes the tool itself and self-installs Playwright so it does not depend on
    # the agent for setup.
    assert "TOOL_HTML_B64" in script
    assert "base64.b64decode(TOOL_HTML_B64)" in script
    assert "playwright" in script and "install" in script
    assert "data-oneline-primary" in script
    # The result always carries navigated and screenshot so infra is detectable.
    assert "navigated" in script and "screenshot" in script
    # No long dash in the generated script.
    assert EM not in script


def test_checks_cover_base_and_criteria():
    checks = build_checks(
        SAMPLE_PLAN["success_criteria"], SAMPLE_PLAN["core_interactions"]
    )
    kinds = [c["kind"] for c in checks]
    assert kinds[:4] == ["load", "primary_present", "primary_responds", "no_errors"]
    assert kinds.count("criterion") == 2


def test_stub_functionality_passes():
    detail = StubFunctionalityJudge().score(GOOD_CANDIDATE, SAMPLE_PLAN)
    assert detail["functionality_score"] == 1.0
    assert detail["failed"] == []
    assert len(detail["passed"]) == 6


def test_judge_emits_valid_judge_scores():
    judge = OnelineJudge(
        functionality=StubFunctionalityJudge(), generate=fake_generate
    )
    scores = judge.judge(GOOD_CANDIDATE, SAMPLE_PLAN)
    validate_judge_scores(scores)
    assert scores["candidate_id"] == "A"
    assert scores["functionality_score"] == 1.0
    # Headline equals the detail headline.
    assert scores["ux_clarity_score"] == scores["ux_clarity"]["ux_clarity_score"]
    assert (
        scores["design_coherence_score"]
        == scores["design_coherence"]["design_coherence_score"]
    )
    # No long dash survived in any field.
    assert EM not in scores["ux_clarity"]["reasoning"]


def test_ux_smell_penalty():
    def smelly(system, user, thinking):
        if "UX Clarity Judge" in system:
            return {
                "sub_scores": {k: 1.0 for k in [
                    "primary_action_dominance", "thumb_reach", "touch_target_size",
                    "visual_simplicity", "feedback_states", "concrete_language",
                ]},
                "production_app_smells": ["signup", "marketing copy"],
                "reasoning": "Two smells present.",
                "improvement_suggestions": [],
            }
        return fake_generate(system, user, thinking)

    judge = OnelineJudge(functionality=StubFunctionalityJudge(), generate=smelly)
    scores = judge.judge(GOOD_CANDIDATE, SAMPLE_PLAN)
    # Mean of sub-scores is 1.0, minus 0.1 per smell, two smells -> 0.8.
    assert scores["ux_clarity_score"] == 0.8


def test_design_violations_penalized():
    judge = OnelineJudge(
        functionality=StubFunctionalityJudge(), generate=off_system_design_generate
    )
    scores = judge.judge(GOOD_CANDIDATE, SAMPLE_PLAN)
    validate_judge_scores(scores)
    # token_conformance dropped to 0.2 and two violations subtract 0.2 more.
    assert scores["design_coherence_score"] < 0.5
    assert scores["design_coherence"]["sub_scores"]["token_conformance"] == 0.2
    assert len(scores["design_coherence"]["system_violations"]) == 2


def test_curator_emits_valid_lesson():
    curator = OnelineCurator(generate=fake_generate)
    lesson = curator.curate(dict(GOOD_CANDIDATE, ux_clarity_score=0.7), SAMPLE_PLAN)
    assert lesson is not None
    assert is_valid_curator_output(lesson)
    # Tags carry the tool category and an always-on tag for the retriever.
    assert "tracker" in lesson["tags"]
    assert any(t in lesson["tags"] for t in ["mobile_first", "primary_cta", "thumb_zone"])
    assert lesson["score_delta"] <= 0
    assert EM not in lesson["lesson_text"]


def test_curator_skips_when_null():
    curator = OnelineCurator(generate=lambda s, u, t: None)
    assert curator.curate(GOOD_CANDIDATE, SAMPLE_PLAN) is None


def test_curator_coerces_off_vocab():
    def off_vocab(system, user, thinking):
        return {
            "tool_category": "habit-thing",
            "lesson_class": "clarity",
            "ux_anti_pattern": "weird_unknown_pattern",
            "tags": [],
            "lesson_text": "Keep the one action obvious and reachable.",
            "bad_pattern": "hidden action",
            "good_pattern": "one bottom action",
            "severity": "huge",
            "score_delta": 0.5,
        }

    lesson = OnelineCurator(generate=off_vocab).curate(GOOD_CANDIDATE, SAMPLE_PLAN)
    assert lesson is not None
    assert is_valid_curator_output(lesson)
    # tool_category fell back to the plan, severity clamped, score_delta forced
    # at or below 0.
    assert lesson["tool_category"] == "tracker"
    assert lesson["severity"] in ("low", "medium", "high")
    assert lesson["score_delta"] <= 0


def test_factories_build_protocol_objects():
    judge = default_judge(generate=fake_generate)
    curator = default_curator(generate=fake_generate)
    assert hasattr(judge, "judge") and callable(judge.judge)
    assert hasattr(curator, "curate") and callable(curator.curate)
    scores = judge.judge(GOOD_CANDIDATE, SAMPLE_PLAN)
    validate_judge_scores(scores)


# --- live functionality path: reuse the sandbox via interactions.create ---

def _marker_output(passed, failed, navigated=True, screenshot="/work/shot.png") -> str:
    payload = {
        "passed": list(passed),
        "failed": list(failed),
        "total": len(passed) + len(failed),
        "screenshot": screenshot,
        "navigated": navigated,
        "loaded": navigated,
        "error": None,
    }
    return "agent wrote files and ran the test\nONELINE_RESULT " + json.dumps(payload) + "\ndone"


class _FakeInteractions:
    """Stands in for client.interactions, recording every create call."""

    def __init__(self, passed, failed):
        self.calls = []
        self._passed = passed
        self._failed = failed

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=_marker_output(self._passed, self._failed),
            environment_id=kwargs.get("environment"),
            id="interaction_test",
            steps=1,
        )


class FakeClient:
    """A google-genai style client whose interactions.create returns a marker."""

    def __init__(self, passed=("primary action responds to a tap",), failed=()):
        self.interactions = _FakeInteractions(list(passed), list(failed))


def _candidate(cid: str, env: str) -> dict:
    return {
        "candidate_id": cid,
        "html": GOOD_HTML,
        "environment_id": env,
        "accent": "#3FB950",
    }


def test_build_run_prompt_embeds_files_and_command():
    prompt = build_run_prompt(
        {"/work/tool.html": "<h1>hi</h1>", "/work/test.py": "print(1)"},
        "python /work/test.py",
    )
    assert "base64.b64decode" in prompt
    assert "/work/tool.html" in prompt and "/work/test.py" in prompt
    assert "python /work/test.py" in prompt
    assert "ONELINE_RESULT" in prompt
    assert EM not in prompt


def test_managed_runner_reuses_environment_via_create():
    fake = FakeClient()
    runner = ManagedAgentsRunner(client=fake)
    out = runner.run(
        "env_reuse_42",
        {"/work/tool.html": GOOD_HTML, "/work/test.py": "print(1)"},
        "python /work/test.py",
    )
    # The reuse call must hit interactions.create with environment set to the
    # candidate's sandbox and the managed agents agent.
    call = fake.interactions.calls[0]
    assert call.get("environment") == "env_reuse_42"
    assert call.get("agent") == "antigravity-preview-05-2026"
    assert "input" in call
    assert "ONELINE_RESULT" in out.output_text


def test_sandbox_functionality_scores_from_marker():
    fake = FakeClient(passed=["loads", "responds"], failed=[])
    judge = SandboxFunctionalityJudge(runner=ManagedAgentsRunner(client=fake))
    detail = judge.score(_candidate("A", "env_aaa"), SAMPLE_PLAN)
    assert detail["functionality_score"] == 1.0
    assert detail["failed"] == []
    assert detail["screenshot"] == "/work/shot.png"


def test_live_judge_completes_without_dropping_all_candidates():
    judge = live_judge(
        runner=ManagedAgentsRunner(client=FakeClient()), generate=fake_generate
    )
    candidates = [
        _candidate("A", "env_a11"),
        _candidate("B", "env_b22"),
        _candidate("C", "env_c33"),
    ]
    scored = []
    for cand in candidates:
        scores = judge.judge(cand, SAMPLE_PLAN)
        validate_judge_scores(scores)
        scored.append(scores)
    # No candidate was dropped, and each ran in its own sandbox (functionality 1.0).
    assert len(scored) == 3
    assert all(s["functionality_score"] == 1.0 for s in scored)
    qualifying = [s for s in scored if s["functionality_score"] >= 0.9]
    assert qualifying, "a winner must be selectable"


def test_infra_false_negative_does_not_kill_working_tool():
    # The exact reported symptom: the in-sandbox test never loaded the tool, so it
    # returned screenshot null and every check failed. That is a test-infra
    # failure, not a tool fault, and must not become a disqualifying 0.0.
    def reuse(environment_id, prompt):
        return SimpleNamespace(
            output_text=_marker_output(
                [], ["tool loads without errors"], navigated=False, screenshot=None
            ),
            environment_id=environment_id,
        )

    # The sandbox judge flags no screenshot plus not navigated as infra.
    sandbox_judge = SandboxFunctionalityJudge(runner=ManagedAgentsRunner(reuse_fn=reuse))
    raised = False
    try:
        sandbox_judge.score(_candidate("A", "env_x"), SAMPLE_PLAN)
    except FunctionalityInfraError:
        raised = True
    assert raised, "screenshot null and not navigated must be flagged as infra"

    # Even under the strictest on_error policy, infra falls back to a default pass,
    # so a working tool is never killed by infra failure.
    fj = FunctionalityJudge(runner=ManagedAgentsRunner(reuse_fn=reuse), on_error="zero")
    detail = fj.score(_candidate("A", "env_x"), SAMPLE_PLAN)
    assert detail["functionality_score"] == 1.0
    assert detail["failed"] == []


def test_missing_marker_is_infra_pass():
    # The agent ran but did not echo the result line. Indeterminate, so pass.
    def reuse(environment_id, prompt):
        return SimpleNamespace(output_text="the agent forgot to echo stdout")

    fj = FunctionalityJudge(runner=ManagedAgentsRunner(reuse_fn=reuse), on_error="zero")
    detail = fj.score(_candidate("A", "env_y"), SAMPLE_PLAN)
    assert detail["functionality_score"] == 1.0


def test_genuine_failure_scores_low_but_infra_passes():
    # Distinguish a tool that loaded and genuinely failed (low score, can be
    # disqualified) from an indeterminate infra failure (default pass).
    def reuse(environment_id, prompt):
        if environment_id == "env_infra":
            raise FunctionalityInfraError("sandbox unreachable")
        if environment_id == "env_broken":
            # Loaded (screenshot captured) but every check failed.
            return SimpleNamespace(
                output_text=_marker_output([], ["c1", "c2", "c3"], navigated=True),
                environment_id=environment_id,
            )
        return SimpleNamespace(
            output_text=_marker_output(["responds"], [], navigated=True),
            environment_id=environment_id,
        )

    judge = live_judge(runner=ManagedAgentsRunner(reuse_fn=reuse), generate=fake_generate)
    ok = judge.judge(_candidate("A", "env_ok"), SAMPLE_PLAN)
    infra = judge.judge(_candidate("B", "env_infra"), SAMPLE_PLAN)
    broken = judge.judge(_candidate("C", "env_broken"), SAMPLE_PLAN)
    for s in (ok, infra, broken):
        validate_judge_scores(s)
    # Infra failure is not a real 0.0; it falls back to a default pass.
    assert infra["functionality_score"] == 1.0
    # A tool that loaded and genuinely failed keeps its real low score.
    assert broken["functionality_score"] == 0.0
    assert ok["functionality_score"] == 1.0


def test_dev_default_judge_falls_back_to_pass_on_sandbox_error():
    from judges.functionality import FunctionalityRunError

    def always_raise(environment_id, prompt):
        raise FunctionalityRunError("down")

    # default_judge uses on_error stub, so a sandbox error becomes a pass and the
    # dev loop never breaks.
    judge = default_judge(
        functionality=FunctionalityJudge(
            runner=ManagedAgentsRunner(reuse_fn=always_raise), on_error="stub"
        ),
        generate=fake_generate,
    )
    scores = judge.judge(_candidate("A", "env_real"), SAMPLE_PLAN)
    validate_judge_scores(scores)
    assert scores["functionality_score"] == 1.0


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # report and continue
            failures += 1
            print("FAIL", fn.__name__, "->", repr(exc))
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
