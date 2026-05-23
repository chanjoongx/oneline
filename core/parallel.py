"""Run independent per-candidate work concurrently.

The implementer and judge clients are I/O-bound: each implementer spawns its own
Gemini Managed Agents sandbox, and each judge calls Gemini and runs Playwright in
that sandbox. A thread pool therefore gives real parallelism while the injected
client Protocols stay synchronous, so the other modules do not have to write
async code and the stubs keep working.

If a client method is async (returns a coroutine), it is run to completion inside
its worker thread, so both sync and async implementations work without a contract
change. core does not depend on ADK; using ADK ParallelAgent here would couple
core to a specific agent type and break the injectable Protocol and the stubs.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from typing import Any, Callable, List, Tuple


def resolve(value: Any) -> Any:
    """If value is awaitable (an async client returned a coroutine), run it to
    completion in the current thread and return its result. Otherwise return it."""
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _worker(fn: Callable, item: Any) -> Any:
    return resolve(fn(item))


def map_settled(
    fn: Callable, items: list, max_workers: "int | None" = None
) -> List[Tuple[bool, Any]]:
    """Apply fn to each item concurrently. Never raises.

    Returns a list of (ok, value_or_exception) in the same order as items, so the
    caller can keep deterministic ordering and decide what to do with failures.
    """
    count = len(items)
    if count == 0:
        return []
    workers = max(1, min(count, max_workers or count))
    settled: List[Tuple[bool, Any]] = [(False, None)] * count
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        index_by_future = {pool.submit(_worker, fn, item): i for i, item in enumerate(items)}
        for future in concurrent.futures.as_completed(index_by_future):
            i = index_by_future[future]
            try:
                settled[i] = (True, future.result())
            except Exception as exc:  # captured per task, not raised
                settled[i] = (False, exc)
    return settled


def map_ordered(fn: Callable, items: list, max_workers: "int | None" = None) -> list:
    """Like map_settled but raises the first failure (lowest index)."""
    settled = map_settled(fn, items, max_workers)
    for i, (ok, value) in enumerate(settled):
        if not ok:
            raise RuntimeError(f"parallel task {i} failed: {value}") from value
    return [value for _ok, value in settled]
