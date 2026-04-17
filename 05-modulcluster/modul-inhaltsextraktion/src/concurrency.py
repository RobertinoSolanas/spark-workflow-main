from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from src.env import ENV, ThrottleConfig
from src.utils.rate_limiter import AsyncRateLimiter

# ---------------------------------------------------------------------------
# Global rate limiter (shared across all model types)
# ---------------------------------------------------------------------------

_global_rate_limiter: AsyncRateLimiter | None = None
_global_semaphore: asyncio.Semaphore | None = None
_global_initialized = False


def _ensure_global_throttle() -> None:
    """Lazily initialize the global rate limiter and semaphore."""
    global _global_rate_limiter, _global_semaphore, _global_initialized
    if _global_initialized:
        return
    cfg = ENV.THROTTLE_GLOBAL
    if cfg.RATE_PER_MINUTE > 0:
        _global_rate_limiter = AsyncRateLimiter(cfg.RATE_PER_MINUTE, per_seconds=60)
    if cfg.MAX_CONCURRENT > 0:
        _global_semaphore = asyncio.Semaphore(cfg.MAX_CONCURRENT)
    _global_initialized = True


class ModelThrottle:
    """Combines a concurrency semaphore with an optional rate limiter.

    ``acquire()`` is an async context manager that:
    1. Acquires the **global** rate limiter (shared API ceiling).
    2. Acquires the **per-model** rate limiter (fairness cap).
    3. Acquires the per-model semaphore to cap concurrent requests.
    """

    def __init__(self, name: str, cfg: ThrottleConfig) -> None:
        self.name = name
        self._semaphore = asyncio.Semaphore(cfg.MAX_CONCURRENT)
        self._rate_limiter: AsyncRateLimiter | None = None
        if cfg.RATE_PER_MINUTE > 0:
            self._rate_limiter = AsyncRateLimiter(cfg.RATE_PER_MINUTE, per_seconds=60)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        """Global rate gate → per-model rate gate → per-model semaphore."""
        _ensure_global_throttle()
        # 1. Global rate limit (shared API ceiling)
        if _global_rate_limiter is not None:
            await _global_rate_limiter.acquire()
        # 2. Per-model rate limit (fairness)
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        # 3. Per-model concurrency semaphore
        async with self._semaphore:
            yield


# ---------------------------------------------------------------------------
# Lazy singleton registry
# ---------------------------------------------------------------------------


Models = Literal[
    "vlm",
    "vlm_summary",
    "summarization",
    "schwerpunktthema",
    "metadata",
    "hypothetical_questions",
    "species_scale",
    "structure",
    "embedding",
]

_registry: dict[Models, ModelThrottle] = {}

_THROTTLE_MAP: dict[Models, ThrottleConfig] = {
    "vlm": ENV.THROTTLE_VLM,
    "vlm_summary": ENV.THROTTLE_VLM_SUMMARY,
    "summarization": ENV.THROTTLE_SUMMARIZATION,
    "schwerpunktthema": ENV.THROTTLE_SCHWERPUNKTTHEMA,
    "metadata": ENV.THROTTLE_METADATA,
    "hypothetical_questions": ENV.THROTTLE_HYPOTHETICAL_QUESTIONS,
    "species_scale": ENV.THROTTLE_SPECIES_SCALE,
    "structure": ENV.THROTTLE_STRUCTURE,
    "embedding": ENV.THROTTLE_EMBEDDING,
}


def get_model_throttle(name: Models) -> ModelThrottle:
    """Creates or returns a ModelThrottle for a given model"""
    if name not in _registry:
        _registry[name] = ModelThrottle(name, _THROTTLE_MAP[name])
    return _registry[name]
