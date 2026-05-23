"""Offline stub mirror of `python -m core.live --events`.

The live dashboard path spawns the core entry point,
`python -m core.live --events "<need>"`, which runs the real pipeline and emits
one JSON object per line on stdout as { "event", "t", "data" }.

This module emits the exact same event shape but over stub deps and a temporary
knowledge base, so the bridge (lib/liveBridge.ts) and the dashboard can be
verified end to end without GEMINI_API_KEY, gcloud, or any network. The live
bridge spawns this only when ONELINE_LIVE_STUB=1; the real path always uses
core.live.

Nothing here touches shared/: lessons are written to a throwaway temp file.
No em dashes anywhere. Hyphens only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

_lock = threading.Lock()
_start = time.perf_counter()


def emit(event: str, data: dict) -> None:
    """One JSON event per line on stdout, matching core.live --events. Thread safe."""
    record = json.dumps(
        {"event": event, "t": round(time.perf_counter() - _start, 3), "data": data},
        ensure_ascii=False,
        default=str,
    )
    with _lock:
        sys.stdout.write(record + "\n")
        sys.stdout.flush()


STUB_PLAN = {
    "rejected": False,
    "rejection_reason": None,
    "suggested_alternative": None,
    "tool_category": "timer",
    "core_interactions": [
        "Start and pause the interval timer",
        "Advance through custom rounds",
    ],
    "data_model": "Rounds and durations held in localStorage. Current round index in memory.",
    "success_criteria": [
        "Starting the timer counts down the first round",
        "Completing a round advances to the next",
    ],
    "candidate_strategies": [
        {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
        {"id": "B", "framework": "tailwind_cdn", "ux_emphasis": "polish"},
        {"id": "C", "framework": "tailwind_cdn", "ux_emphasis": "minimal_whitespace"},
    ],
}

STUB_KB_SEED = {
    "lessons": [
        {
            "id": "lesson_001",
            "created_at": "2026-05-23T13:10:00Z",
            "tool_category": "tracker",
            "lesson_class": "ux_clarity",
            "ux_anti_pattern": "buried_primary_action",
            "tags": ["mobile_first", "tracker", "primary_cta", "touch_targets"],
            "lesson_text": "Primary action must sit in the bottom third for thumb reach.",
            "bad_pattern": "top-right action button on a tall single-screen layout",
            "good_pattern": "bottom-center sticky full-width action",
            "severity": "high",
            "score_delta": -0.4,
            "applied_count": 0,
            "prevented_repeats": 0,
        }
    ]
}


def main(argv) -> int:
    need = " ".join(a for a in argv if not a.startswith("--")).strip()
    if not need:
        need = os.environ.get("ONELINE_NEED", "").strip()
    if not need:
        need = "interval timer 4 rounds"

    emit("start", {"need": need, "judge": "stub", "deploy": "stub"})

    try:
        from core import kb as kb_mod, orchestrator
    except Exception as e:
        traceback.print_exc()
        emit("error", {"stage": "import", "message": str(e)})
        return 1

    # Stub deps over a throwaway knowledge base, so shared/ is never touched.
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="-oneline-kb.json", delete=False, encoding="utf-8"
    )
    json.dump(STUB_KB_SEED, tmp)
    tmp.flush()
    tmp.close()
    deps = orchestrator.make_stub_deps(STUB_PLAN, kb_path=Path(tmp.name))
    deps.on_event = emit  # same {event, t, data} shape core.live --events uses

    try:
        result = orchestrator.run(need, deps)
    except Exception as e:
        traceback.print_exc()
        emit("error", {"stage": "run", "message": str(e)})
        return 1

    try:
        lessons = kb_mod.list_lessons(deps.kb_path)
    except Exception:
        lessons = []

    status = result.get("status")
    deployment = result.get("deployment") or {}
    selection = result.get("selection") or {}
    winner = (
        selection["winner"].get("candidate_id")
        if isinstance(selection.get("winner"), dict)
        else None
    )
    emit(
        "done",
        {
            "status": status,
            "winner": winner,
            "url": deployment.get("url"),
            "service": deployment.get("service"),
            "fallback": bool(deployment.get("fallback")),
            "lessons_added": result.get("lessons_added", []),
            "prevented_repeats": result.get("prevented_repeats", []),
            "reason": result.get("reason"),
            # Inlined so the dashboard knowledge base panel shows growth offline.
            # The real path reads the on-disk knowledge base instead.
            "lessons": lessons,
        },
    )
    return 0 if status == "deployed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
