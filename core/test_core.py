"""Offline self-check for core. No network, no API key.

Run directly:   python core/test_core.py
Or with pytest: pytest core/test_core.py

Tests use a temporary copy of the knowledge base so the committed seed file in
shared/ is never modified.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import time

# Allow running as a plain script from anywhere by putting the repo root on path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import kb, orchestrator, parallel, retriever, schemas, selector, stubs  # noqa: E402
from core.config import KB_PATH  # noqa: E402

SAMPLE_PLAN = {
    "rejected": False,
    "rejection_reason": None,
    "suggested_alternative": None,
    "tool_category": "tracker",
    "core_interactions": ["Increment the count", "Reset the count at midnight"],
    "data_model": "count and last-reset date in localStorage",
    "success_criteria": ["Tapping the button increases the count", "Count persists on reload"],
    "candidate_strategies": [
        {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
        {"id": "B", "framework": "tailwind_cdn", "ux_emphasis": "polish"},
        {"id": "C", "framework": "tailwind_cdn", "ux_emphasis": "minimal_whitespace"},
    ],
}


def _temp_kb() -> pathlib.Path:
    tmp_dir = tempfile.mkdtemp(prefix="oneline-kb-")
    path = pathlib.Path(tmp_dir) / "knowledge_base.json"
    shutil.copyfile(KB_PATH, path)
    return path


def test_sample_plan_valid():
    schemas.validate(SAMPLE_PLAN, "plan")


def test_seed_kb_lessons_valid():
    for lesson in kb.list_lessons():
        schemas.validate(lesson, "lesson")


def test_retriever_shape_and_threshold():
    out = retriever.retrieve(SAMPLE_PLAN, kb.list_lessons())
    schemas.validate(out, "retrieved_lessons")
    assert len(out["retrieved_lessons"]) <= 5
    assert all(item["relevance_score"] >= 0.5 for item in out["retrieved_lessons"])
    # The seed lesson uses a broadly applicable anti-pattern, so it is retrieved.
    assert any(item["id"] == "lesson_001" for item in out["retrieved_lessons"])


def test_selector_picks_highest_and_validates():
    candidates = [
        {"candidate_id": "A", "environment_id": "e", "functionality_score": 1.0,
         "ux_clarity_score": 0.80, "design_coherence_score": 0.70},
        {"candidate_id": "B", "environment_id": "e", "functionality_score": 1.0,
         "ux_clarity_score": 0.92, "design_coherence_score": 0.88},
        {"candidate_id": "C", "environment_id": "e", "functionality_score": 0.50,
         "ux_clarity_score": 0.99, "design_coherence_score": 0.99},
    ]
    selection = selector.select_winner(candidates)
    schemas.validate(selection, "selection")
    assert selection["winner"]["candidate_id"] == "B"
    assert {loser["candidate_id"] for loser in selection["losers"]} == {"A", "C"}


def test_selector_tie_break_on_ux():
    # Same final score, B has higher ux_clarity, so B wins.
    candidates = [
        {"candidate_id": "A", "environment_id": "e", "functionality_score": 1.0,
         "ux_clarity_score": 0.80, "design_coherence_score": 1.00},
        {"candidate_id": "B", "environment_id": "e", "functionality_score": 1.0,
         "ux_clarity_score": 0.94, "design_coherence_score": 0.804},
    ]
    selection = selector.select_winner(candidates)
    assert selection["winner"]["candidate_id"] == "B"


def test_selector_no_winner():
    candidates = [
        {"candidate_id": "A", "environment_id": "e", "functionality_score": 0.5,
         "ux_clarity_score": 0.9, "design_coherence_score": 0.9},
    ]
    selection = selector.select_winner(candidates)
    schemas.validate(selection, "selection")
    assert selection["winner"] is None
    assert selection["reason"]


def test_kb_append_roundtrip():
    path = _temp_kb()
    before = len(kb.list_lessons(path))
    lesson = kb.append_lesson(
        {
            "tool_category": "timer",
            "lesson_class": "ux_clarity",
            "ux_anti_pattern": "missing_feedback_state",
            "tags": ["mobile_first", "timer", "feedback"],
            "lesson_text": "Flash a confirmation on every tap so the user knows it registered.",
            "bad_pattern": "no visible response on tap",
            "good_pattern": "a brief highlight on tap",
            "severity": "medium",
            "score_delta": -0.2,
        },
        path,
    )
    schemas.validate(lesson, "lesson")
    assert lesson["id"] == "lesson_002"
    assert lesson["applied_count"] == 0 and lesson["prevented_repeats"] == 0
    assert len(kb.list_lessons(path)) == before + 1


def test_full_pipeline_stub():
    path = _temp_kb()
    deps = orchestrator.make_stub_deps(SAMPLE_PLAN, kb_path=path)
    result = orchestrator.run("a counter that resets at midnight", deps)
    assert result["status"] == "deployed"
    schemas.validate(result["selection"], "selection")
    assert result["selection"]["winner"]["candidate_id"] == "B"
    assert result["deployment"]["url"]
    for candidate in result["candidates"]:
        schemas.validate(candidate, "candidate")
    for scores in result["judge_scores"].values():
        schemas.validate(scores, "judge_scores")
    # Losers A and C scored ux below 0.9 in the stub judge, so lessons are added.
    assert len(result["lessons_added"]) >= 1
    # The applied lesson plus the new ones are all in the temp kb.
    assert len(kb.list_lessons(path)) > 1


def test_rejected_plan_short_circuits():
    rejected = dict(
        SAMPLE_PLAN,
        rejected=True,
        rejection_reason="needs accounts and a shared server",
        suggested_alternative="a single-screen personal version with localStorage",
    )
    deps = orchestrator.make_stub_deps(rejected, kb_path=_temp_kb())
    result = orchestrator.run("a multiplayer social leaderboard app", deps)
    assert result["status"] == "rejected"
    assert result["suggested_alternative"]


def test_max_candidates_one():
    path = _temp_kb()
    deps = orchestrator.make_stub_deps(SAMPLE_PLAN, kb_path=path, max_candidates=1)
    result = orchestrator.run("a single counter", deps)
    assert len(result["candidates"]) == 1
    assert result["status"] == "deployed"


def test_parallel_map_settled_order_and_errors():
    def fn(x):
        if x == 2:
            raise ValueError("boom")
        return x * 10

    settled = parallel.map_settled(fn, [1, 2, 3])
    assert settled[0] == (True, 10)
    assert settled[1][0] is False and isinstance(settled[1][1], ValueError)
    assert settled[2] == (True, 30)


def test_parallel_map_ordered_raises_first():
    def fn(x):
        if x in (2, 3):
            raise ValueError(f"bad {x}")
        return x

    try:
        parallel.map_ordered(fn, [1, 2, 3])
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "task 1" in str(exc)


def test_parallel_supports_async_callables():
    async def afn(x):
        return x + 1

    assert parallel.map_ordered(afn, [1, 2, 3]) == [2, 3, 4]


class _SlowImplementer:
    def __init__(self, delay=0.2):
        self._inner = stubs.StubImplementer()
        self._delay = delay

    def build_candidate(self, strategy, brief, lessons):
        time.sleep(self._delay)
        return self._inner.build_candidate(strategy, brief, lessons)


def test_build_runs_concurrently():
    deps = orchestrator.make_stub_deps(
        SAMPLE_PLAN, kb_path=_temp_kb(), implementer=_SlowImplementer(0.2)
    )
    start = time.perf_counter()
    result = orchestrator.run("a counter", deps)
    elapsed = time.perf_counter() - start
    assert result["status"] == "deployed"
    assert len(result["candidates"]) == 3
    # Three 0.2s builds in parallel finish well under the 0.6s sequential time.
    assert elapsed < 0.5, f"build was not concurrent, took {elapsed:.2f}s"


class _FlakyImplementer:
    def __init__(self, fail_id="B"):
        self._inner = stubs.StubImplementer()
        self._fail_id = fail_id

    def build_candidate(self, strategy, brief, lessons):
        if strategy["id"] == self._fail_id:
            raise RuntimeError("sandbox spawn failed")
        return self._inner.build_candidate(strategy, brief, lessons)


def test_build_resilient_to_one_failure():
    deps = orchestrator.make_stub_deps(
        SAMPLE_PLAN, kb_path=_temp_kb(), implementer=_FlakyImplementer("B")
    )
    result = orchestrator.run("a counter", deps)
    assert result["status"] == "deployed"
    assert {c["candidate_id"] for c in result["candidates"]} == {"A", "C"}
    assert result["build_errors"][0]["candidate_id"] == "B"
    assert result["selection"]["winner"]["candidate_id"] in {"A", "C"}


class _DeadImplementer:
    def build_candidate(self, strategy, brief, lessons):
        raise RuntimeError("sandbox down")


def test_all_builds_fail_is_reported():
    deps = orchestrator.make_stub_deps(
        SAMPLE_PLAN, kb_path=_temp_kb(), implementer=_DeadImplementer()
    )
    result = orchestrator.run("a counter", deps)
    assert result["status"] == "build_failed"
    assert len(result["build_errors"]) == 3


class _AsyncImplementer:
    def __init__(self):
        self._inner = stubs.StubImplementer()

    async def build_candidate(self, strategy, brief, lessons):
        return self._inner.build_candidate(strategy, brief, lessons)


def test_async_implementer_supported():
    deps = orchestrator.make_stub_deps(
        SAMPLE_PLAN, kb_path=_temp_kb(), implementer=_AsyncImplementer()
    )
    result = orchestrator.run("a counter", deps)
    assert result["status"] == "deployed"
    assert len(result["candidates"]) == 3


def test_planner_normalizes_messy_plan():
    from core import planner

    messy = {
        "tool_category": "interval_timer_thing",
        "core_interactions": "start the timer",
        "data_model": "rounds and durations in localStorage",
        "success_criteria": ["the timer counts down"],
        "candidate_strategies": [
            {"id": "A", "framework": "react", "ux_emphasis": "high contrast, big type, web audio"},
        ],
    }
    normalized = planner._normalize(messy)
    schemas.validate(normalized, "plan")
    assert normalized["tool_category"] == "utility"
    assert isinstance(normalized["core_interactions"], list)
    emphases = [s["ux_emphasis"] for s in normalized["candidate_strategies"]]
    assert emphases == ["speed_minimal", "polish", "minimal_whitespace"]


def test_planner_strips_visual_success_criteria():
    from core import planner

    plan = {
        "tool_category": "timer",
        "core_interactions": [
            "Start, pause, and reset the timer",
            "Visual countdown with color-coded states for work and rest",
        ],
        "data_model": "rounds in localStorage",
        "success_criteria": [
            "The timer runs 8 rounds of 90s work and 30s rest",
            "The screen background changes color drastically between phases",
            "Use red for work and green for rest",
        ],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan)
    schemas.validate(out, "plan")
    assert any("8 rounds" in c for c in out["success_criteria"])
    assert all("color" not in c.lower() for c in out["success_criteria"])
    assert all("red for work" not in c.lower() for c in out["success_criteria"])
    assert all("color-coded" not in c.lower() for c in out["core_interactions"])


def test_planner_keeps_behavioral_and_non_color_words():
    from core import planner

    plan = {
        "tool_category": "tracker",
        "core_interactions": ["Log a glass of orange juice", "Reset the count at midnight"],
        "data_model": "count in localStorage",
        "success_criteria": ["Tapping increments the count", "The count persists on reload"],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan)
    schemas.validate(out, "plan")
    assert "Log a glass of orange juice" in out["core_interactions"]
    assert len(out["success_criteria"]) == 2


def test_planner_visual_only_lists_get_behavioral_fallback():
    from core import planner

    plan = {
        "tool_category": "timer",
        "core_interactions": ["color-coded phases"],
        "data_model": "x",
        "success_criteria": ["the background changes color between phases"],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan)
    schemas.validate(out, "plan")
    assert len(out["core_interactions"]) == 1
    assert len(out["success_criteria"]) == 1
    assert all("color" not in c.lower() for c in out["success_criteria"])
    assert all("color" not in c.lower() for c in out["core_interactions"])


def test_planner_strips_unrequested_scope_creep():
    from core import planner

    plan = {
        "tool_category": "calculator",
        "core_interactions": [
            "Enter the bill, tip percent, and number of people",
            "Save each calculation to a history list with a timestamp",
        ],
        "data_model": "values in memory",
        "success_criteria": [
            "The per-person amount updates instantly as inputs change",
            "Saved calculations persist in a history list and can be cleared all at once",
            "Toggle rounding to round each share up or down",
        ],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan, need="a tip calculator that splits a bill between people")
    schemas.validate(out, "plan")
    blob = " ".join(out["core_interactions"] + out["success_criteria"]).lower()
    assert "history" not in blob
    assert "timestamp" not in blob
    assert "rounding" not in blob and "round each" not in blob
    assert "clear all" not in blob and "cleared all" not in blob
    assert any("per-person amount updates" in c for c in out["success_criteria"])
    assert any("Enter the bill" in c for c in out["core_interactions"])


def test_planner_keeps_explicitly_requested_features():
    from core import planner

    plan = {
        "tool_category": "calculator",
        "core_interactions": ["Enter the bill and tip"],
        "data_model": "x",
        "success_criteria": ["Saved calculations persist in a history list across refresh"],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan, need="a tip calculator with saved history")
    schemas.validate(out, "plan")
    assert any("history" in c.lower() for c in out["success_criteria"])


def test_planner_keeps_persistence_for_stateful_category():
    from core import planner

    plan = {
        "tool_category": "tracker",
        "core_interactions": ["Tap to add a glass of water"],
        "data_model": "count in localStorage",
        "success_criteria": ["The history of today's entries persists across refresh"],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan, need="a water intake tracker")
    schemas.validate(out, "plan")
    assert any("history" in c.lower() for c in out["success_criteria"])


def test_planner_caps_list_length():
    from core import planner

    plan = {
        "tool_category": "timer",
        "core_interactions": ["alpha", "bravo", "charlie", "delta", "echo"],
        "data_model": "x",
        "success_criteria": ["one", "two", "three", "four"],
        "candidate_strategies": [],
    }
    out = planner._normalize(plan, need="a timer")
    schemas.validate(out, "plan")
    assert len(out["core_interactions"]) <= 3
    assert len(out["success_criteria"]) <= 3


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
