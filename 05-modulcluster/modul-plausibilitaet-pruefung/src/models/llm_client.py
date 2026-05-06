"""
Provides the LLMClient class for interacting
with OpenAI-compatible APIs (via LiteLLM proxy) asynchronously.
"""

import asyncio
import logging
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from src.config.config import LLMProfile, config
from src.config.env import ENV

logger = logging.getLogger(__name__)

_shared_client: AsyncOpenAI | None = None


def _get_shared_client() -> AsyncOpenAI:
    global _shared_client
    if _shared_client is None:
        _shared_client = AsyncOpenAI(
            base_url=ENV.LITELLM.BASE_URL,
            api_key=ENV.LITELLM.MASTER_KEY,
            timeout=config.LITELLM_CLIENT.TIMEOUT_SECONDS,
            max_retries=0,
        )
    return _shared_client


class LLMClient:
    def __init__(
        self,
        profile: LLMProfile | None = None,
    ) -> None:
        self.profile = profile or LLMProfile(model_name=ENV.LITELLM.MODEL)
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Initialise (or return cached) AsyncOpenAI client pointing at LiteLLM."""
        if self._client:
            return self._client
        logger.info(f"Init client for {ENV.LITELLM.BASE_URL}")
        self._client = AsyncOpenAI(
            base_url=ENV.LITELLM.BASE_URL,
            api_key=ENV.LITELLM.MASTER_KEY,
            timeout=config.LITELLM_CLIENT.TIMEOUT_SECONDS,
            max_retries=config.LITELLM_CLIENT.MAX_RETRIES,
        )
        return self._client

    async def ainvoke(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        output_format: type | None = None,
    ) -> Any:
        """
        Send a prompt to the LLM asynchronously.
        Args:
            user_prompt: The user query.
            system_prompt: Optional system prompt.
            output_format: Optional output format.
        """
        client = self._get_client()
        messages = cast(list[ChatCompletionMessageParam], [{"role": "user", "content": user_prompt}])
        if system_prompt:
            messages.insert(0, cast(ChatCompletionMessageParam, {"role": "system", "content": system_prompt}))
        if output_format:
            response = await client.beta.chat.completions.parse(
                messages=messages,
                model=self.profile.model_name,
                temperature=self.profile.temperature,
                top_p=self.profile.top_p,
                max_completion_tokens=self.profile.max_tokens,
                reasoning_effort=self.profile.reasoning_effort,
                response_format=output_format,
            )
            return response.choices[0].message.parsed
        else:
            response = await client.chat.completions.create(  # type: ignore[call-overload]
                messages=messages,
                model=self.profile.model_name,
                temperature=self.profile.temperature,
                top_p=self.profile.top_p,
                max_completion_tokens=self.profile.max_tokens,
                reasoning_effort=self.profile.reasoning_effort,
                response_format=output_format,
            )
            return (response.choices[0].message.content or "").strip()

    def invoke(
        self,
        prompt: str,
    ) -> Any:
        """
        Send a prompt to the LLM synchronously.
        Args:
            prompt: The user query.
        """
        return asyncio.run(
            self.ainvoke(
                user_prompt=prompt,
            )
        )
