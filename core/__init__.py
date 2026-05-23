"""Oneline core: planner, retriever, selector, orchestration, knowledge base I/O.

Every product model call uses gemini-3.5-flash. The selector and the default
retriever are deterministic. No em dashes anywhere, hyphens only.

Submodules are imported lazily by callers so importing the package stays cheap
and free of side effects (no network, no SDK requirement at import time).
"""

__all__ = [
    "config",
    "schemas",
    "prompts",
    "planner",
    "retriever",
    "selector",
    "kb",
    "interfaces",
    "orchestrator",
]
