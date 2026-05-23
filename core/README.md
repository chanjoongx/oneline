# core

Orchestration for Oneline: the planner, the retriever, the selector, the loop
that wires everything together, and knowledge base I/O. Every model call is
`gemini-3.5-flash`. The selector and the default retriever are deterministic.

## Modules

| Module | What it does |
|---|---|
| `planner.py` | `plan(need)` runs the Planner (gemini-3.5-flash, thinking high), returns a Plan |
| `retriever.py` | `retrieve(plan, lessons)` deterministic tag relevance, returns RetrievedLessons. `gemini_retrieve(...)` is the spec model path |
| `selector.py` | `select_winner(scored_candidates)` deterministic, functionality-gated, weighted |
| `kb.py` | read and write `shared/knowledge_base.json`, append curated lessons, bump metrics |
| `orchestrator.py` | `run(need, deps)` the full pipeline |
| `parallel.py` | run candidate builds and judges concurrently (thread pool, async-aware) |
| `interfaces.py` | the Protocols core depends on (implementer, judge, curator, deployer) |
| `stubs.py` | Phase 1 stand-ins so the loop runs before the other modules deliver |
| `live.py` | composition root: wire the real sandbox, judges, and web, run one request end to end |
| `gemini.py` | the gemini-3.5-flash JSON call wrapper |
| `schemas.py` | load and validate against `shared/schemas` |
| `prompts.py` | planner and retriever system prompts |

## Run

```bash
# offline self-check, no API key needed
python core/test_core.py

# core loop with the real planner and stub externals (needs GEMINI_API_KEY)
python -m core "a 4 by 4 minute interval timer with 1 minute rests"

# full live end to end with the real sandbox, judges, and web components
python -m core.live "interval timer, 90 seconds work 30 rest, 8 rounds"
python -m core.live --judge default --dry-deploy "..."   # variations
```

`GEMINI_API_KEY` is read from the environment only. It is never hardcoded,
logged, or committed.

## Live integration status

`core/live.py` is the composition root that wires the real components
(`sandbox.ManagedAgentsImplementer`, `judges.live_judge` or `default_judge` with
`default_curator`, `web.deployer.CloudRunDeployer`) into the loop and reports each
stage through the orchestrator `on_event` hook (also available for the web SSE
stream).

Verified end to end against the live APIs: plan, retrieve, three parallel Managed
Agents sandbox builds, real UX and design judges, deterministic selection, a real
Cloud Run deploy with a returned URL, and curation that adds lessons. Two
composition-root settings are applied in `live.py`: the implementer is built with
`model=None` (the interactions API accepts only agent or model, not both, and the
agent carries gemini-3.5-flash), and `default_judge` completes the loop when the
strict in-sandbox functionality run is unavailable.

One open cross-module item: the strict `live_judge` functionality run needs a
run-in-environment call the current google-genai interactions API does not expose
(`run_in_environment`, `run`, `execute`, `exec` are all absent), so it falls back
to a functionality pass under `default_judge`. Running a command in an existing
sandbox goes through `interactions.create(environment=<id>, input=...)`; aligning
the functionality runner to that shape is owned by the judges and sandbox
modules.

## Selector math

```
gate = 0.9
qualifying = [c for c in candidates if c.functionality_score >= gate]
if not qualifying: winner is null, with a reason
final = 0.40 * functionality + 0.35 * ux_clarity + 0.25 * design_coherence
winner = max(qualifying, key = (final, ux_clarity))   # tie-break on ux_clarity
```

## Integration: what the other modules implement

core depends on four interfaces (see `interfaces.py`) and is handed objects that
satisfy them through `orchestrator.Deps`. core never imports from `sandbox/`,
`judges/`, or `web/`.

```python
from core import orchestrator

deps = orchestrator.make_default_deps(
    implementer=my_sandbox_client,   # sandbox/: build_candidate(strategy, brief, lessons) -> Candidate
    judge=my_judge_client,           # judges/:  judge(candidate, plan) -> JudgeScores
    curator=my_curator,              # judges/:  curate(loser, plan) -> curator_output or None
    deployer=my_deploy_client,       # web/:     deploy(winner_html) -> {url, service, ts}
)
result = orchestrator.run("a counter that resets at midnight", deps)
```

Until a real component lands, the matching stub is used, so the loop runs end to
end today. Swap one in at a time.

Contract shapes (Plan, Candidate, JudgeScores, Selection, Lesson,
RetrievedLessons) are defined in `shared/schemas`. The canonical candidate
identifier is `candidate_id`. No em dashes in any output, including generated
HTML.

## Concurrency

The three candidates build concurrently, one thread per candidate, and are
judged concurrently the same way. The work is I/O-bound (each implementer spawns
its own Managed Agents sandbox), so a thread pool gives real parallelism while
the injected client Protocols stay synchronous. An async client (a coroutine
`build_candidate` or `judge`) is also supported: it runs to completion inside its
worker thread. core does not depend on ADK, which keeps the injectable stubs and
one-at-a-time integration working. `Deps.max_workers` caps the pool (default 3).

A single build or judge failure does not sink the request. Survivors proceed and
a failed candidate is recorded under `build_errors` or `judge_errors`. Loser
curation runs after deploy, off the critical path, and stays sequential because
core is the only writer to the knowledge base.

Because builds and judges are concurrent, the implementer and judge clients must
be safe to call from multiple threads at once. Each candidate uses its own
sandbox, so this is the natural shape.

## `run` result

`orchestrator.run` returns a dict with `status` one of `deployed`, `rejected`,
`no_winner`, `build_failed`, or `judge_failed`, plus `plan`, `retrieved_lessons`,
`candidates`, `judge_scores`, `selection`, `deployment`, `lessons_added`,
`prevented_repeats`, and `build_errors` or `judge_errors` when a candidate fails,
as the run reaches each stage.
