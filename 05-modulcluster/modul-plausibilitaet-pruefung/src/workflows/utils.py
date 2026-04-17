"""Utility helpers for plausibility workflows."""

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
    if not items:
        return []

    ok: list[R] = []
    in_flight: dict[asyncio.Task[R], T] = {}
    next_i = 0
    scheduled_since_flush = 0

    async def schedule_one() -> None:
        nonlocal next_i, scheduled_since_flush
        task = workflow.asyncio.ensure_future(fn(items[next_i]))
        in_flight[task] = items[next_i]
        next_i += 1
        scheduled_since_flush += 1

        # force framework flush every 30 schedules
        if scheduled_since_flush >= 30:
            scheduled_since_flush = 0
            await asyncio.sleep(1)  # or your framework's cheapest reliable flush point

    # initial fill
    while next_i < len(items) and len(in_flight) < concurrency:
        await schedule_one()

    while in_flight:
        done, _ = await workflow.wait(
            in_flight.keys(),
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            in_flight.pop(task)
            ok.append(task.result())

        # refill window
        while next_i < len(items) and len(in_flight) < concurrency:
            await schedule_one()

    return ok
