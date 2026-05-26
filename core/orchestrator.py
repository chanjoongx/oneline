"""The orchestration loop. Wires planner to retriever to the parallel
implementers to the judges to the selector to the deployer, and routes losers to
the curator. External steps (implementer, judge, deployer, curator) are injected
through Deps so the other modules plug in their real implementations and tests
run fully offline.

Pipeline:
  need -> Planner -> Plan
       -> Retriever(Plan, KB) -> RetrievedLessons   (and bump applied_count)
       -> Implementer x N      -> Candidate per strategy
       -> Judge per candidate  -> JudgeScores
       -> Selector             -> Selection
            winner -> Deployer -> url + QR
            losers -> Curator  -> Lesson(s) -> knowledge_base.json
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import config, kb as kb_mod, parallel, planner as planner_mod
from . import retriever as retriever_mod, schemas, selector as selector_mod, stubs
from .interfaces import Curator, Deployer, ImplementerClient, JudgeClient

PlannerFn = Callable[[str], dict]
RetrieverFn = Callable[[dict, list], dict]


@dataclass
class Deps:
    """Everything the loop calls into. Inject real implementations here."""

    implementer: ImplementerClient
    judge: JudgeClient
    deployer: Deployer
    curator: Curator
    planner: PlannerFn
    retriever: Optional[RetrieverFn] = None
    kb_path: Any = config.KB_PATH
    max_candidates: int = 3
    max_workers: int = config.MAX_PARALLEL_BUILDS
    validate: bool = True
    on_event: Optional[Callable[[str, dict], None]] = None

    def __post_init__(self):
        if self.retriever is None:
            self.retriever = lambda plan, lessons: retriever_mod.retrieve(
                plan, lessons, validate=self.validate
            )


def make_default_deps(**overrides) -> Deps:
    """Real planner (gemini-3.5-flash) and deterministic retriever, with stubs for
    implementer, judge, deployer, and curator until the sandbox, judges, and web modules deliver.
    Override any field by keyword as real components land."""
    base = dict(
        implementer=stubs.StubImplementer(),
        judge=stubs.StubJudge(),
        deployer=stubs.StubDeployer(),
        curator=stubs.StubCurator(),
        planner=lambda need: planner_mod.plan(need),
    )
    base.update(overrides)
    return Deps(**base)


def make_stub_deps(plan: dict, **overrides) -> Deps:
    """Fully offline deps. The planner returns the given fixed plan. For tests."""
    base = dict(
        implementer=stubs.StubImplementer(),
        judge=stubs.StubJudge(),
        deployer=stubs.StubDeployer(),
        curator=stubs.StubCurator(),
        planner=lambda need: plan,
    )
    base.update(overrides)
    return Deps(**base)


def _brief(need: str, plan: dict) -> str:
    return "\n".join(
        [
            f"User need: {need}",
            f"Tool category: {plan.get('tool_category')}",
            f"Core interactions: {plan.get('core_interactions')}",
            f"Data model: {plan.get('data_model')}",
            f"Success criteria: {plan.get('success_criteria')}",
        ]
    )


def _prevented(winner: dict, judge_scores_by_id: dict, retrieved: list, all_lessons: list) -> list:
    """Heuristic for the repeat-failures metric: a retrieved lesson counts as
    prevented when the winner shows none of its anti-pattern in the judge
    violations."""
    scores = judge_scores_by_id.get(winner["candidate_id"], {})
    violations = set()
    for v in scores.get("design_coherence", {}).get("system_violations", []):
        violations.add(str(v).lower())
    for v in scores.get("ux_clarity", {}).get("production_app_smells", []):
        violations.add(str(v).lower())
    by_id = {lesson["id"]: lesson for lesson in all_lessons}
    prevented = []
    for item in retrieved:
        lesson = by_id.get(item["id"])
        if not lesson:
            continue
        anti = (lesson.get("ux_anti_pattern") or "").lower()
        if anti and not any(anti in v or v in anti for v in violations):
            prevented.append(item["id"])
    return prevented


def _emit(deps: Deps, event: str, payload: dict) -> None:
    """Notify the optional stage observer. Never breaks the run."""
    callback = getattr(deps, "on_event", None)
    if callback is None:
        return
    try:
        callback(event, payload)
    except Exception:
        pass


def run(need: str, deps: Optional[Deps] = None) -> dict:
    """Run one request through the full pipeline. Returns an aggregate result."""
    deps = deps or make_default_deps()
    result: dict = {"need": need, "status": "running"}

    # 1. Plan
    plan = deps.planner(need)
    if deps.validate:
        schemas.validate(plan, "plan")
    result["plan"] = plan
    _emit(deps, "plan", {"plan": plan})
    if plan.get("rejected"):
        result["status"] = "rejected"
        result["rejection_reason"] = plan.get("rejection_reason")
        result["suggested_alternative"] = plan.get("suggested_alternative")
        _emit(deps, "rejected", {
            "reason": plan.get("rejection_reason"),
            "alternative": plan.get("suggested_alternative"),
        })
        return result

    # 2. Retrieve lessons and record that they were applied
    all_lessons = kb_mod.list_lessons(deps.kb_path)
    retrieved = deps.retriever(plan, all_lessons)
    result["retrieved_lessons"] = retrieved["retrieved_lessons"]
    retrieved_ids = [item["id"] for item in retrieved["retrieved_lessons"]]
    if retrieved_ids:
        kb_mod.bump_applied(retrieved_ids, deps.kb_path)
    _emit(deps, "retrieve", {"retrieved_lessons": retrieved["retrieved_lessons"]})

    # 3. Build candidates concurrently, one thread per candidate. Each builds in
    #    its own Managed Agents sandbox, so this is a true parallel build. Schema
    #    validation runs serially after the gather. A single build failure does
    #    not sink the request; survivors proceed.
    strategies = plan.get("candidate_strategies", [])[: deps.max_candidates]
    brief = _brief(need, plan)
    _emit(deps, "build_start", {"strategies": strategies})

    def _build(strategy):
        candidate = parallel.resolve(
            deps.implementer.build_candidate(strategy, brief, retrieved["retrieved_lessons"])
        )
        # Per-candidate event from the worker thread, so the dashboard column for
        # this candidate fills the moment its sandbox finishes. on_event must be
        # thread-safe (the live emitters lock around the write).
        _emit(deps, "candidate_built", {
            "candidate_id": candidate.get("candidate_id"),
            "accent": candidate.get("accent"),
            "framework": candidate.get("framework"),
            "ux_emphasis": candidate.get("ux_emphasis"),
            "steps": candidate.get("steps"),
            "rationale": candidate.get("rationale"),
            "html": candidate.get("html"),
        })
        return candidate

    candidates = []
    build_errors = []
    for strategy, (ok, value) in zip(
        strategies, parallel.map_settled(_build, strategies, max_workers=deps.max_workers)
    ):
        cid = strategy.get("id")
        if not ok:
            build_errors.append({"candidate_id": cid, "error": str(value)})
            continue
        if deps.validate:
            try:
                schemas.validate(value, "candidate")
            except Exception as exc:
                build_errors.append({"candidate_id": cid, "error": f"invalid candidate: {exc}"})
                continue
        candidates.append(value)
    result["candidates"] = candidates
    if build_errors:
        result["build_errors"] = build_errors
    _emit(deps, "build_done", {
        "built": [c["candidate_id"] for c in candidates],
        "build_errors": build_errors,
    })
    if not candidates:
        result["status"] = "build_failed"
        result["reason"] = "No candidate could be built. Try a simpler request."
        return result

    # 4. Judge candidates concurrently, then merge headline scores. A judge
    #    failure drops that candidate; the rest stay selectable.
    def _judge(candidate):
        scores = parallel.resolve(deps.judge.judge(candidate, plan))
        _emit(deps, "candidate_judged", {
            "candidate_id": scores.get("candidate_id", candidate.get("candidate_id")),
            "functionality_score": scores.get("functionality_score"),
            "ux_clarity_score": scores.get("ux_clarity_score"),
            "design_coherence_score": scores.get("design_coherence_score"),
            "functionality": scores.get("functionality"),
            "ux_clarity": scores.get("ux_clarity"),
            "design_coherence": scores.get("design_coherence"),
        })
        return scores

    scored = []
    judge_scores_by_id = {}
    judge_errors = []
    for candidate, (ok, value) in zip(
        candidates, parallel.map_settled(_judge, candidates, max_workers=deps.max_workers)
    ):
        cid = candidate["candidate_id"]
        if not ok:
            judge_errors.append({"candidate_id": cid, "error": str(value)})
            continue
        if deps.validate:
            try:
                schemas.validate(value, "judge_scores")
            except Exception as exc:
                judge_errors.append({"candidate_id": cid, "error": f"invalid judge scores: {exc}"})
                continue
        judge_scores_by_id[cid] = value
        scored.append(selector_mod.merge_scores(candidate, value))
    result["judge_scores"] = judge_scores_by_id
    if judge_errors:
        result["judge_errors"] = judge_errors
    _emit(deps, "judge_done", {
        "scored": [c["candidate_id"] for c in scored],
        "judge_errors": judge_errors,
    })
    if not scored:
        result["status"] = "judge_failed"
        result["reason"] = "No candidate could be judged."
        return result

    # 5. Select the winner
    selection = selector_mod.select_winner(scored, validate=deps.validate)
    result["selection"] = selection
    if not selection.get("winner"):
        result["status"] = "no_winner"
        result["reason"] = selection.get("reason")
        _emit(deps, "no_winner", {"reason": selection.get("reason")})
        return result
    _emit(deps, "select", {
        "winner": selection["winner"]["candidate_id"],
        "rationale": selection.get("rationale"),
    })

    # 6. Deploy the winner
    _emit(deps, "deploy_start", {"winner": selection["winner"]["candidate_id"]})
    result["deployment"] = deps.deployer.deploy(selection["winner"]["html"])
    result["status"] = "deployed"
    _emit(deps, "deploy_done", {"deployment": result["deployment"]})

    # 7. Curate losers into lessons and persist them
    added = []
    for loser in selection.get("losers", []):
        curator_output = deps.curator.curate(loser, plan)
        if curator_output:
            lesson = kb_mod.append_lesson(curator_output, deps.kb_path, validate=deps.validate)
            if lesson:
                added.append(lesson["id"])
    result["lessons_added"] = added
    _emit(deps, "curate_done", {"lessons_added": added})

    # 8. Repeat-failures metric
    prevented = _prevented(
        selection["winner"], judge_scores_by_id, retrieved["retrieved_lessons"], all_lessons
    )
    if prevented:
        kb_mod.bump_prevented(prevented, deps.kb_path)
    result["prevented_repeats"] = prevented

    return result
