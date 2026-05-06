import asyncio
import logging

import httpx

from src.concurrency import get_model_throttle
from src.env import ENV

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 25
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0  # seconds


class EmbeddingClient:
    """Async HTTP client for OpenAI-compatible embedding APIs.

    Creates a single ``httpx.AsyncClient`` on init; call :meth:`close` (or use
    as an async context-manager) when done to release the connection pool.
    """

    def __init__(self, timeout: float = 60.0) -> None:
        self._base_url = f"{ENV.LITELLM_BASE_URL}/embeddings"
        self._model = ENV.EMBEDDING_MODEL
        api_key = ENV.LITELLM_MASTER_KEY.get_secret_value()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "EmbeddingClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Send a single embedding request for a batch of texts."""
        payload = {"model": self._model, "input": texts}
        resp = await self._client.post(self._base_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def _embed_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch with retries for transient network/server errors."""
        async with get_model_throttle("embedding").acquire():
            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES):
                try:
                    return await self._embed_batch(texts)
                except (
                    httpx.ConnectTimeout,
                    httpx.ConnectError,
                    httpx.PoolTimeout,
                ) as e:
                    last_exc = e
                    wait = _RETRY_BACKOFF_BASE**attempt
                    logger.warning(
                        "Embedding connect error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500:
                        last_exc = e
                        wait = _RETRY_BACKOFF_BASE**attempt
                        logger.warning(
                            "Embedding server error %d (attempt %d/%d), retrying in %.1fs",
                            e.response.status_code,
                            attempt + 1,
                            _MAX_RETRIES,
                            wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise
            raise last_exc  # type: ignore[misc]

    async def aembed_many(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings, automatically sub-batching to avoid timeouts."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            try:
                embeddings = await self._embed_batch_with_retry(batch)
                all_embeddings.extend(embeddings)
            except httpx.HTTPError as e:
                logger.error(
                    "Embedding request failed for batch %d-%d: %s",
                    i,
                    i + len(batch),
                    e,
                    exc_info=True,
                )
                raise
        return all_embeddings

    async def aembed(self, text: str) -> list[float]:
        """Convenience method for a single text."""
        embeddings = await self.aembed_many([text])
        return embeddings[0]
