# Oneline judges

The three-layer judge and the curator. This directory owns scoring and lesson
extraction. It codes against the shapes the core module committed in `shared/`; it
never edits `shared/`, `core/`, `sandbox/`, or `web/`.

Every model based judge and the curator use `gemini-3.5-flash`, no other model.
Functionality is deterministic (Playwright in the managed sandbox). All output is
JSON, with no long dashes in any field.

## Integration point

core injects two objects through `make_default_deps`:

```python
from judges import default_judge, default_curator
from core import orchestrator

deps = orchestrator.make_default_deps(
    judge=default_judge(),      # JudgeClient: judge(candidate, plan) -> JudgeScores
    curator=default_curator(),  # Curator: curate(loser, plan) -> curator_output | None
)
result = orchestrator.run("a counter that resets at midnight", deps)
```

- `default_judge()` is an `OnelineJudge`. It satisfies the `JudgeClient` Protocol
  in `core/interfaces.py`.
- `default_curator()` is an `OnelineCurator`. It satisfies the `Curator` Protocol.

For the live demo, use `live_judge()` instead of `default_judge()`. It runs the
real sandbox functionality test, reusing each candidate's `environment_id`. A
tool that loads but fails its interactions keeps its real low score and can be
disqualified; an indeterminate run (sandbox unreachable, no result reported, or
the tool never loaded with no screenshot) is treated as test-infrastructure
failure and falls back to a default pass, so a working tool is never killed by
flaky infra.

## The three judges

| Sub-judge | Method | Model | Thinking |
|---|---|---|---|
| Functionality | Playwright in the candidate sandbox | deterministic | none |
| UX clarity | grandmother test rubric on the HTML | gemini-3.5-flash | high |
| Design coherence | conformance to the shared design system | gemini-3.5-flash | medium |

`OnelineJudge.judge` runs all three and assembles one `JudgeScores` object that
matches `shared/schemas/judge_scores.schema.json`: the three headline numbers the
selector reads, plus the three detail objects for the dashboard and the curator.

### 1. Functionality (`functionality.py`)

Deterministic, no model call. `generate_playwright_test` builds a headless test
from `plan.success_criteria` and `plan.core_interactions`. The test renders the
tool at 390px, finds the dominant interactive control as the primary action,
taps it and the other controls, and reports each plan check as passed or failed
plus a screenshot. The headline is `passed / max(total, 1)`; the selector gate is
0.9.

`SandboxFunctionalityJudge` reuses the candidate's `environment_id`, the very
Gemini Managed Agents sandbox that built the tool, writes the HTML and the test
into it, and runs `python /work/test.py` in that environment. Build and test
happen in the same managed sandbox. google-genai has no run-in-environment
method; the managed agents API resumes a sandbox (its files, packages, and
state) by passing `environment=<environment_id>` to `interactions.create`,
confirmed against the live docs (the Continue the conversation section of the
managed agents quickstart). `ManagedAgentsRunner` prefers the sandbox module's reuse
helper (`run_in_existing_environment` or `reuse_environment`) so the exact create
shape lives in one place, and falls back to a direct
`interactions.create(agent=..., environment=<environment_id>, input=...)`.

The generated test is self-contained: it writes the tool to `/work/tool.html`
itself, self-installs Playwright with Chromium if missing, loads
`file:///work/tool.html`, waits for load, exercises the plan interactions, and
screenshots to `/work/shot.png`. It always prints a single `ONELINE_RESULT` line
carrying `navigated` and `screenshot`, so the judge can tell a real failure from
a test-infrastructure failure.

`FunctionalityJudge` (the default) routes real environment ids to the sandbox run
and stub ids to `StubFunctionalityJudge`, which returns pass so the end-to-end
pipe completes before sandboxes are wired. Three outcomes:

- The tool loaded and the checks ran: the real score is returned and honored,
  even when low. A tool that loads but fails its interactions is genuinely broken
  and keeps that low score, which can disqualify it.
- The run was indeterminate (sandbox unreachable, no result reported, or the tool
  never loaded and no screenshot was captured): a `FunctionalityInfraError`. The
  judge falls back to a default pass so a working tool is never killed by flaky
  test infra. This is the critical guard against false negatives.
- Some other unexpected error: the `on_error` policy decides, `stub` falls back
  to pass (default), `zero` disqualifies just that candidate, `raise` surfaces it.

### 2. UX clarity (`ux_clarity.py`)

The grandmother test: can a 70-year-old find and use the primary action within 30
seconds, no instruction. Six sub-scores: primary_action_dominance, thumb_reach,
touch_target_size, visual_simplicity, feedback_states, concrete_language. The
headline is the mean of the sub-scores minus 0.1 for each production-app smell
(signup, onboarding, marketing copy, share buttons, and the rest), computed in
code so the rubric math never drifts on the model's arithmetic.

### 3. Design coherence (`design_coherence.py`)

Conformance to the shared design system, not taste. Sub-scores: token_conformance,
hero_discipline, typography_consistency, spatial_consistency, restraint. The
prompt embeds the six approved accent hexes (#5B8DEF, #3FB950, #E3A008, #A371F7,
#F85149, #2DD4BF) and the base token hexes, so a second accent or an off-system
color is caught and named in `system_violations`. The headline is the mean of the
sub-scores minus a penalty per violation, so system violations are penalized
heavily.

## The curator (`curator.py`)

`OnelineCurator.curate` turns each loser into one universal, reusable UX lesson
matching the `curator_output` subset of `shared/schemas/lesson.schema.json`, or
returns `None` when nothing generalizable is found. It coerces the model output
onto the shared vocabulary (tool categories, anti-patterns, severities) and
guarantees every lesson carries the tool category and at least one always-on
mobile tag, so the tag based retriever can match it. The core write helper later
adds id, created_at, applied_count, and prevented_repeats.

## Output discipline, confirmed

- The functionality judge reuses the candidate's `environment_id` so Playwright
  runs in the same managed sandbox that built the tool.
- All three judges emit the shared `JudgeScores` shape; every object is validated
  against `shared/schemas/judge_scores.schema.json` in the self-check.
- The curator writes `curator_output` lessons the retriever can match by tag;
  validated against the `curator_output` subschema in the self-check.
- The design judge references the six approved accent hexes so a second accent or
  an off-system color is caught.
- No long dashes in any emitted field; the sanitizer strips them recursively.

## Run the self-check

Offline, no network, no API key (every model call is faked):

```bash
python judges/test_judges.py
# or
pytest judges/test_judges.py
```

## Files

| File | Role |
|---|---|
| `judge.py` | `OnelineJudge`, assembles the three-layer `JudgeScores` |
| `functionality.py` | Playwright test generator, sandbox runner, functionality judges |
| `ux_clarity.py` | UX clarity scoring, gemini-3.5-flash thinking high |
| `design_coherence.py` | design coherence scoring, gemini-3.5-flash thinking medium |
| `curator.py` | `OnelineCurator`, loser to reusable lesson |
| `prompts.py` | system prompts, with the approved accents embedded |
| `gemini_client.py` | the gemini-3.5-flash JSON call |
| `schema_check.py` | validation against the shared contract plus the vocabulary |
| `sanitize.py` | long dash stripping and score coercion |
| `config.py` | model, thinking budgets, viewport, approved accents |
| `test_judges.py` | offline self-check |
