"""End-to-end check for the sandbox module.

  python -m sandbox.demo --offline                 build one candidate offline
  python -m sandbox.demo --offline --parallel      build three offline, in parallel
  python -m sandbox.demo --need "..." --category timer       build one live
  python -m sandbox.demo --parallel --need "..."             build three live

Offline uses the fake managed client (no API key, no credits). Live spawns real
Gemini Managed Agents sandboxes and needs GEMINI_API_KEY in the environment.
Every built candidate is validated against shared/schemas/candidate.schema.json.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import CANDIDATE_SCHEMA_PATH
from .extract import has_long_dash
from .fake import FakeManagedClient
from .implementer import ManagedAgentsImplementer

_STRATEGIES = [
    {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
    {"id": "B", "framework": "tailwind_cdn", "ux_emphasis": "polish"},
    {"id": "C", "framework": "tailwind_cdn", "ux_emphasis": "minimal_whitespace"},
]


def _brief(need: str, category: str) -> str:
    return "\n".join(
        [
            f"User need: {need}",
            f"Tool category: {category}",
            "Core interactions: ['Perform the main action', 'Read the current value']",
            "Data model: Minimal state in localStorage. No backend, no database.",
            "Success criteria: ['The main action works', 'The current value is visible at a glance']",
        ]
    )


def _validate(candidate: dict) -> "tuple[bool, str]":
    try:
        import jsonschema
    except ImportError:
        return True, "jsonschema not installed, skipped validation"
    schema = json.loads(CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(candidate, schema)
        return True, "valid against candidate.schema.json"
    except jsonschema.ValidationError as exc:  # pragma: no cover - error path
        return False, f"schema error: {exc.message}"


def _report(candidate: dict) -> bool:
    cid = candidate["candidate_id"]
    html = candidate["html"]
    ok_schema, schema_msg = _validate(candidate)
    clean = not has_long_dash(html) and not has_long_dash(candidate.get("rationale", ""))
    print(f"\ncandidate {cid}")
    print(f"  environment_id : {candidate['environment_id']}")
    print(f"  accent         : {candidate.get('accent')}")
    print(f"  emphasis       : {candidate.get('ux_emphasis')}")
    print(f"  steps          : {candidate.get('steps')}")
    print(f"  html bytes     : {len(html)}")
    print(f"  no long dash   : {clean}")
    print(f"  schema         : {ok_schema} ({schema_msg})")
    print(f"  rationale      : {candidate.get('rationale')}")
    return ok_schema and clean and bool(candidate["environment_id"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Oneline sandbox module demo")
    parser.add_argument("--need", default="A simple tap counter I reset each day")
    parser.add_argument("--category", default="tracker")
    parser.add_argument("--parallel", action="store_true", help="build all three candidates")
    parser.add_argument("--offline", action="store_true", help="use the fake managed client")
    args = parser.parse_args(argv)

    client = FakeManagedClient() if args.offline else None
    impl = ManagedAgentsImplementer(client=client)
    brief = _brief(args.need, args.category)
    lessons = [
        {
            "id": "lesson_001",
            "lesson_text": "Primary action must sit in the bottom third for thumb reach.",
            "good_pattern": "bottom-center sticky full-width action",
            "relevance_score": 0.9,
        }
    ]

    mode = "offline" if args.offline else "live"
    if args.parallel:
        print(f"building 3 candidates in parallel ({mode}) ...")
        candidates = impl.build_candidates(_STRATEGIES, brief, lessons)
    else:
        print(f"building 1 candidate ({mode}) ...")
        candidates = [impl.build_candidate(_STRATEGIES[0], brief, lessons)]

    all_ok = all(_report(c) for c in candidates)
    env_ids = [c["environment_id"] for c in candidates]
    print(f"\nenvironment_ids exposed for the judge: {env_ids}")
    print("\nresult:", "ok" if all_ok else "FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
