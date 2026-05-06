# src/utils/sliding_window.py
"""Generic sliding-window executor for Temporal workflows.

Keeps *concurrency* tasks in flight at all times.  When one finishes the
next item is immediately started — no fixed-batch idle time.

Returns ``(successes, failed_items)`` so callers can decide what to retry.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from temporalio import workflow

T = TypeVar("T")
R = TypeVar("R")


async def sliding_window(
    items: list[T],
    fn: Callable[[T], Awaitable[R]],
    concurrency: int,
) -> tuple[list[R], list[T]]:
    """Process *items* through *fn* with a sliding concurrency window.

    Args:
        items: Work units to process.
        fn: Async callable that processes one item.  **Must raise** on
            failure so the item is captured in the *failed* list.
        concurrency: Maximum number of concurrent tasks.

    Returns:
        ``(ok, failed)`` — *ok* contains successful results, *failed*
        contains the original items whose *fn* call raised.
    """
    if not items:
        return [], []

    ok: list[R] = []
    failed: list[T] = []

    # Map in-flight futures back to their source item
    in_flight: dict[asyncio.Task[R], T] = {}
    next_i = 0

    # Seed the initial window
    for _ in range(min(concurrency, len(items))):
        task = asyncio.ensure_future(fn(items[next_i]))
        in_flight[task] = items[next_i]
        next_i += 1

    # Drain: as each task completes, backfill from remaining items
    while in_flight:
        done, _ = await workflow.wait(in_flight.keys(), return_when=asyncio.FIRST_COMPLETED)
        for completed in done:
            item = in_flight.pop(completed)
            try:
                ok.append(completed.result())
            except Exception:
                failed.append(item)

            # Backfill
            if next_i < len(items):
                new_task = asyncio.ensure_future(fn(items[next_i]))
                in_flight[new_task] = items[next_i]
                next_i += 1

    return ok, failed
