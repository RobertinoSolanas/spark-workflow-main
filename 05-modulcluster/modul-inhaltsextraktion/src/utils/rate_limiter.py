# src/utils/rate_limiter.py
"""
Provides an asynchronous rate limiter to control the frequency of operations.
"""

import asyncio
import threading
import time
from _thread import LockType


class AsyncRateLimiter:
    _last_call_time: float
    delay: float
    _lock: LockType

    """
    A thread-safe, asynchronous rate limiter to control the frequency of operations.
    This ensures that operations do not exceed a specified rate, even when called
    from multiple threads with different event loops.
    """

    def __init__(self, rate_limit: int, per_seconds: int = 60) -> None:
        """
        Initializes the rate limiter.
        Args:
            rate_limit (int): The number of allowed requests per time period.
            per_seconds (int): The time period in seconds (default is 60 for per minute).
        """
        if rate_limit <= 0:
            self.delay = 0
        else:
            self.delay = per_seconds / rate_limit

        self._lock = threading.Lock()  # Use a thread-safe lock
        self._last_call_time = 0

    async def acquire(self) -> None:
        """
        Acquires a slot, waiting if necessary to maintain the rate limit.
        This should be called before the operation you want to rate limit.
        """
        if self.delay == 0:
            return

        with self._lock:
            # This block is thread-safe. It calculates when the next operation
            # is allowed to run and updates the timestamp for the *next* caller.
            next_call_time = self._last_call_time + self.delay
            current_time = time.monotonic()

            wait_duration = next_call_time - current_time
            if wait_duration < 0:
                wait_duration = 0

            # Update the last call time based on when this operation will finish waiting
            self._last_call_time = current_time + wait_duration

        if wait_duration > 0:
            # The actual sleep happens outside the lock, so it doesn't block
            # other threads, only the current asyncio task.
            await asyncio.sleep(wait_duration)
