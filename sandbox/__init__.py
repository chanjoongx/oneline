"""Oneline sandbox module: the Gemini Managed Agents integration.

One isolated managed sandbox per candidate. The implementer prompt runs with
gemini-3.5-flash inside the sandbox, returns a single-file HTML tool, and the
Candidate carries the environment_id so the functionality judge can run
Playwright in the same sandbox that built the tool.

core injects the implementer:
    from sandbox import ManagedAgentsImplementer
    deps = orchestrator.make_default_deps(implementer=ManagedAgentsImplementer())
"""
from __future__ import annotations

from .client import (
    create_interaction,
    default_playwright_test,
    ensure_playwright_in_environment,
    get_client,
    parse_file_report,
    parse_run_report,
    read_file_from_environment,
    reuse_environment,
    run_functionality_test,
    run_in_existing_environment,
    write_file_to_environment,
)
from .extract import html_problems, is_html_complete
from .implementer import IncompleteHTMLError, ManagedAgentsImplementer
from .prompts import render_implementer_prompt

__all__ = [
    "ManagedAgentsImplementer",
    "IncompleteHTMLError",
    "render_implementer_prompt",
    "create_interaction",
    "reuse_environment",
    "run_in_existing_environment",
    "write_file_to_environment",
    "read_file_from_environment",
    "ensure_playwright_in_environment",
    "run_functionality_test",
    "default_playwright_test",
    "parse_run_report",
    "parse_file_report",
    "is_html_complete",
    "html_problems",
    "get_client",
]
