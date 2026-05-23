"""Oneline judges: functionality, UX clarity, design coherence, and the curator.

Integration point for core. core injects through make_default_deps:

    from judges import default_judge, default_curator
    deps = orchestrator.make_default_deps(
        judge=default_judge(),
        curator=default_curator(),
    )

default_judge() satisfies the JudgeClient Protocol (judge(candidate, plan) ->
JudgeScores) and default_curator() satisfies the Curator Protocol
(curate(loser, plan) -> curator_output | None) from core/interfaces.py.

The three model based judges and the curator all use gemini-3.5-flash, no other
model. The functionality judge is deterministic and reuses the candidate's
environment_id so Playwright runs in the same managed sandbox that built the
tool. Every emitted field is free of long dashes.

Two judge factories:
- default_judge() pairs the real UX and design judges with FunctionalityJudge,
  which runs the real sandbox test for real environment ids and returns pass for
  stub ids, so the end-to-end pipe completes before sandboxes are wired.
- live_judge() runs the real sandbox functionality test, reusing each candidate's
  environment_id, for the live demo once real environment ids flow from
  the sandbox module. A tool that loads but fails its interactions keeps its real low
  score and can be disqualified; an indeterminate run (sandbox unreachable, no
  result reported, or the tool never loaded and no screenshot was captured) is
  treated as test-infrastructure failure and falls back to a default pass, so a
  working tool is never killed by flaky infra.
"""
from __future__ import annotations

from .curator import OnelineCurator, normalize_curator_output
from .design_coherence import score_design_coherence
from .functionality import (
    FunctionalityInfraError,
    FunctionalityJudge,
    FunctionalityRunError,
    ManagedAgentsRunner,
    SandboxFunctionalityJudge,
    StubFunctionalityJudge,
    build_run_prompt,
    generate_playwright_test,
)
from .judge import OnelineJudge, assemble_judge_scores
from .ux_clarity import score_ux_clarity

__all__ = [
    "OnelineJudge",
    "OnelineCurator",
    "FunctionalityJudge",
    "SandboxFunctionalityJudge",
    "StubFunctionalityJudge",
    "FunctionalityInfraError",
    "FunctionalityRunError",
    "ManagedAgentsRunner",
    "build_run_prompt",
    "generate_playwright_test",
    "score_ux_clarity",
    "score_design_coherence",
    "assemble_judge_scores",
    "normalize_curator_output",
    "default_judge",
    "live_judge",
    "default_curator",
]


def default_judge(**overrides) -> OnelineJudge:
    """Real UX and design judges plus the resilient functionality judge.

    Real environment ids run the Playwright test in the candidate sandbox; stub
    ids and sandbox hiccups return pass so the loop never breaks. Override any
    OnelineJudge argument by keyword (functionality, generate, ux_thinking,
    design_thinking)."""
    return OnelineJudge(**overrides)


def live_judge(runner: "ManagedAgentsRunner | None" = None, **overrides) -> OnelineJudge:
    """The full judge for the live demo: real sandbox functionality run.

    Reuses each candidate's environment_id to run Playwright in the very sandbox
    that built it. A tool that loads but fails its interactions keeps its real low
    score and can be disqualified. An indeterminate run (sandbox unreachable, no
    result reported, or the tool never loaded with no screenshot) is treated as
    test-infrastructure failure and falls back to a default pass, so a working
    tool is never killed by flaky infra. Use this once real environment ids are
    flowing."""
    functionality = FunctionalityJudge(runner=runner, on_error="stub")
    overrides.setdefault("functionality", functionality)
    return OnelineJudge(**overrides)


def default_curator(**overrides) -> OnelineCurator:
    """The gemini-3.5-flash curator that writes tag matchable lessons."""
    return OnelineCurator(**overrides)
