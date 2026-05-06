import asyncio
import logging

from openai import AsyncOpenAI

from src.config.config import config
from src.config.env import ENV, LiteLLMEmbeddingModel

logger = logging.getLogger(__name__)

_shared_client: AsyncOpenAI | None = None


def _get_shared_client() -> AsyncOpenAI:
    """Return (or lazily create) the process-wide AsyncOpenAI instance."""
    global _shared_client
    if _shared_client is None:
        _shared_client = AsyncOpenAI(
            base_url=ENV.LITELLM.BASE_URL,
            api_key=ENV.LITELLM.MASTER_KEY,
            timeout=config.EMBEDDING.TIMEOUT_SECONDS,
            max_retries=0,
        )
    return _shared_client


class EmbeddingClient:
    def __init__(
        self,
        model: LiteLLMEmbeddingModel | None = None,
    ) -> None:
        self.model = model or ENV.LITELLM.EMBEDDING_MODEL
        self.base_url = f"{ENV.LITELLM.BASE_URL}/embeddings"

    async def aembed_many(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for multiple texts in a single request."""
        if not texts:
            return []

        client = _get_shared_client()

        for attempt in range(config.EMBEDDING.MAX_RETRIES + 1):
            try:
                response = await client.embeddings.create(
                    model=self.model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as exc:
                is_last_attempt = attempt >= config.EMBEDDING.MAX_RETRIES
                if is_last_attempt:
                    raise exc
                logger.warning(
                    "Embedding request failed on attempt %s/%s with %s. Retrying in %ss.",
                    attempt + 1,
                    config.EMBEDDING.MAX_RETRIES + 1,
                    type(exc).__name__,
                    config.EMBEDDING.RETRY_INTERVAL_SECONDS,
                    exc_info=True,
                )
                await asyncio.sleep(config.EMBEDDING.RETRY_INTERVAL_SECONDS)
        raise AssertionError("Unreachable: embedding retry loop must return or raise")

    async def aembed(self, text: str) -> list[float]:
        """Convenience method for a single text."""
        embeddings = await self.aembed_many([text])
        return embeddings[0]
