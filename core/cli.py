"""Run one request from the command line.

    python -m core "a 4 by 4 minute interval timer with 1 minute rests"

Uses make_default_deps, which runs the real gemini-3.5-flash planner and the
deterministic retriever, with stub implementer, judge, deployer, and curator
until the other modules plug in their real components. Needs GEMINI_API_KEY.
"""
from __future__ import annotations

import json
import sys

from . import orchestrator


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: python -m core "the tool I need"')
        return 2
    need = " ".join(argv)
    result = orchestrator.run(need)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
