"""Live end-to-end run. Wires the real sandbox, judges, and web components into
the core loop and runs one request, reporting every stage.

    python -m core.live "interval timer, 90 seconds work 30 rest, 8 rounds"
    python -m core.live --judge default            # non-strict functionality
    python -m core.live --dry-deploy "..."         # simulate the deploy
    python -m core.live --events "..."             # JSON-lines event stream on stdout

Needs GEMINI_API_KEY in the environment. The real Cloud Run deploy runs unless
--dry-deploy or ONELINE_DEPLOY_DRYRUN=1. This is the only module in core that
imports sandbox, judges, and web; the core library itself stays decoupled and is
wired here at the composition root.

With --events, stdout carries exactly one JSON object per line, one per pipeline
phase, for a parent process (the web dashboard) to read line by line. All human
logs, warnings, and tracebacks go to stderr, so stdout stays clean JSON.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import time
import traceback

# Allow running as a plain script by putting the repo root on the path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import orchestrator  # noqa: E402
from core.config import gemini_api_key  # noqa: E402

DEFAULT_NEED = "interval timer, 90 seconds work 30 rest, 8 rounds"


def build_live_deps(judge_mode: str = "live", deploy_dry: bool = False):
    """Construct Deps with the real implementer, judge, curator, and deployer."""
    from sandbox import ManagedAgentsImplementer
    from judges import default_curator, default_judge, live_judge
    from web.deployer import CloudRunDeployer

    judge = live_judge() if judge_mode == "live" else default_judge()
    deployer = CloudRunDeployer(dry_run=True) if deploy_dry else CloudRunDeployer()
    # model=None: the live interactions API rejects setting both agent and model
    # ("only one can be set"). The managed agent antigravity-preview-05-2026 is
    # itself configured for gemini-3.5-flash, so omitting model uses the confirmed
    # working call shape and stays compliant.
    implementer = ManagedAgentsImplementer(model=None)
    return orchestrator.make_default_deps(
        implementer=implementer,
        judge=judge,
        curator=default_curator(),
        deployer=deployer,
    )


def _printer():
    """Human-readable stage log to stdout. Thread-safe (per-candidate events come
    from worker threads)."""
    start = time.perf_counter()
    lock = threading.Lock()

    def on_event(event: str, payload: dict) -> None:
        elapsed = time.perf_counter() - start
        line = f"[{elapsed:6.1f}s] {event}"
        if event == "plan":
            plan = payload["plan"]
            ids = [s.get("id") for s in plan.get("candidate_strategies", [])]
            line += f": category={plan.get('tool_category')} strategies={ids}"
        elif event == "rejected":
            line += f": {payload.get('reason')} -> {payload.get('alternative')}"
        elif event == "retrieve":
            line += f": {len(payload['retrieved_lessons'])} lesson(s) applied"
        elif event == "build_start":
            line += f": spawning sandboxes for {[s.get('id') for s in payload['strategies']]}"
        elif event == "candidate_built":
            line += (f": {payload['candidate_id']} built"
                     f" (accent {payload.get('accent')}, {payload.get('steps')} steps)")
        elif event == "build_done":
            line += f": built {payload['built']}"
            if payload["build_errors"]:
                line += f"  build_errors={payload['build_errors']}"
        elif event == "candidate_judged":
            line += (f": {payload['candidate_id']} scored"
                     f" func={payload.get('functionality_score')}"
                     f" ux={payload.get('ux_clarity_score')}"
                     f" design={payload.get('design_coherence_score')}")
        elif event == "judge_done":
            line += f": scored {payload['scored']}"
            if payload["judge_errors"]:
                line += f"  judge_errors={payload['judge_errors']}"
        elif event == "select":
            line += f": winner {payload['winner']} ({payload['rationale']})"
        elif event == "no_winner":
            line += f": {payload.get('reason')}"
        elif event == "deploy_start":
            line += f": deploying winner {payload['winner']}"
        elif event == "deploy_done":
            dep = payload["deployment"]
            tag = ", FALLBACK" if dep.get("fallback") else ""
            line += f": {dep.get('url')} (service={dep.get('service')}{tag})"
        elif event == "curate_done":
            line += f": lessons added {payload['lessons_added']}"
        with lock:
            print(line, flush=True)

    return on_event


def _json_emitter(out=None):
    """One JSON object per line on stdout, for a parent process to stream. Each
    line is {"event": str, "t": seconds_since_start, "data": {...}}. Thread-safe
    so per-candidate events from worker threads never interleave."""
    out = out or sys.stdout
    start = time.perf_counter()
    lock = threading.Lock()

    def on_event(event: str, payload: dict) -> None:
        record = json.dumps(
            {"event": event, "t": round(time.perf_counter() - start, 3), "data": payload},
            ensure_ascii=False,
            default=str,
        )
        with lock:
            out.write(record + "\n")
            out.flush()

    return on_event


def _trunc_html(obj):
    """Return a copy of a candidate-like dict with html replaced by its length."""
    out = dict(obj)
    if isinstance(out.get("html"), str):
        out["html"] = f"<{len(out['html'])} chars>"
    return out


def _summarize(result: dict) -> dict:
    out = dict(result)
    if out.get("candidates"):
        out["candidates"] = [_trunc_html(c) for c in out["candidates"]]
    selection = out.get("selection")
    if isinstance(selection, dict):
        selection = dict(selection)
        if isinstance(selection.get("winner"), dict):
            selection["winner"] = _trunc_html(selection["winner"])
        if selection.get("losers"):
            selection["losers"] = [_trunc_html(loser) for loser in selection["losers"]]
        out["selection"] = selection
    return out


def _run_human(need: str, args) -> int:
    """Default mode: human-readable stage log and a result summary on stdout."""
    if not gemini_api_key():
        print("GEMINI_API_KEY is not set in the environment; cannot run live.",
              file=sys.stderr)
        return 2

    print(f"need:   {need}")
    print(f"judge:  {args.judge}")
    print(f"deploy: {'dry-run' if args.dry_deploy else 'real (gcloud)'}\n")

    try:
        deps = build_live_deps(args.judge, args.dry_deploy)
    except Exception:
        print("FAILED to wire the real components:\n", file=sys.stderr)
        traceback.print_exc()
        return 1
    deps.on_event = _printer()

    start = time.perf_counter()
    try:
        result = orchestrator.run(need, deps)
    except Exception:
        print("\nPIPELINE RAISED before completing:\n", file=sys.stderr)
        traceback.print_exc()
        return 1
    elapsed = time.perf_counter() - start

    status = result.get("status")
    print(f"\nstatus: {status}   total: {elapsed:.1f}s")
    if status == "deployed":
        print("URL:    " + result["deployment"]["url"])
    print("\n--- result summary ---")
    print(json.dumps(_summarize(result), ensure_ascii=False, indent=2, default=str))
    return 0 if status == "deployed" else 1


def _run_events(need: str, args) -> int:
    """Machine mode: JSON-lines event stream on stdout for a parent process.
    Human logs, warnings, and tracebacks go to stderr only."""
    emit = _json_emitter()
    emit("start", {
        "need": need,
        "judge": args.judge,
        "deploy": "dry-run" if args.dry_deploy else "real",
    })
    if not gemini_api_key():
        emit("error", {"stage": "preflight", "message": "GEMINI_API_KEY is not set"})
        return 2
    try:
        deps = build_live_deps(args.judge, args.dry_deploy)
    except Exception as exc:
        traceback.print_exc()
        emit("error", {"stage": "wire", "message": str(exc)})
        return 1
    deps.on_event = emit
    try:
        result = orchestrator.run(need, deps)
    except Exception as exc:
        traceback.print_exc()
        emit("error", {"stage": "run", "message": str(exc)})
        return 1

    status = result.get("status")
    deployment = result.get("deployment") or {}
    selection = result.get("selection") or {}
    winner = (selection["winner"].get("candidate_id")
              if isinstance(selection.get("winner"), dict) else None)
    emit("done", {
        "status": status,
        "winner": winner,
        "url": deployment.get("url"),
        "service": deployment.get("service"),
        "fallback": bool(deployment.get("fallback")),
        "lessons_added": result.get("lessons_added", []),
        "prevented_repeats": result.get("prevented_repeats", []),
        "reason": result.get("reason"),
    })
    return 0 if status == "deployed" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Oneline live end-to-end run")
    parser.add_argument("need", nargs="*", help="the tool need in plain language")
    parser.add_argument("--judge", choices=["live", "default"], default="live",
                        help="live forces the strict in-sandbox functionality run")
    parser.add_argument("--dry-deploy", action="store_true",
                        help="simulate the Cloud Run deploy instead of calling gcloud")
    parser.add_argument("--events", action="store_true",
                        help="stream one JSON event per line on stdout for a parent process")
    args = parser.parse_args(argv)
    need = " ".join(args.need) if args.need else DEFAULT_NEED
    return _run_events(need, args) if args.events else _run_human(need, args)


if __name__ == "__main__":
    raise SystemExit(main())
