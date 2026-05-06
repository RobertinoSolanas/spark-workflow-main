"""Workflow utility helpers."""

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
) -> list[R]:
    """Process items through fn with a sliding concurrency window."""
    if not items:
        return []

    ok: list[R] = []
    in_flight: dict[asyncio.Task[R], T] = {}
    next_i = 0

    for _ in range(min(concurrency, len(items))):
        task = asyncio.ensure_future(fn(items[next_i]))
        in_flight[task] = items[next_i]
        next_i += 1

    while in_flight:
        done, _ = await workflow.wait(in_flight.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            in_flight.pop(task)
            ok.append(task.result())

            if next_i < len(items):
                next_task = asyncio.ensure_future(fn(items[next_i]))
                in_flight[next_task] = items[next_i]
                next_i += 1

    return ok
