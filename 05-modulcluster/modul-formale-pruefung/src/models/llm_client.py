"""
Provides the LLMClient class for interacting
with OpenAI-compatible APIs asynchronously and synchronously,
with configurable response handling.
"""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI
from prompt_injection.prompt_defense import wrap_system_prompt

from src.config.config import (
    LLMProfile,
    config,
)
from src.config.env import ENV

logger = logging.getLogger(__name__)


class LLMClient:
    """
    A lightweight, configuration-driven wrapper for OpenAI-compatible APIs.
    """

    def __init__(
        self,
        profile: LLMProfile,
        system_prompt: str,
        response_format: Any = None,
    ):
        """
        Args:
            profile: The configuration profile (temperature, etc.) for the model.
            system_prompt: System prompt.
            response_format: Optional Pydantic model for structured output.
        """
        self.profile = profile
        self.system_prompt = wrap_system_prompt(system_prompt)
        self.response_format = response_format
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Ensure the client is initialized."""
        if self._client:
            return self._client
        self._client = AsyncOpenAI(
            base_url=ENV.LITELLM.BASE_URL,
            api_key=ENV.LITELLM.MASTER_KEY,
            timeout=config.LITELLM_CLIENT.TIMEOUT_SECONDS,
            max_retries=0,
        )
        return self._client

    async def ainvoke(
        self,
        prompt: str,
    ) -> Any:
        """
        Send a prompt to the LLM asynchronously.
        Args:
            prompt: The user query. Note that this prompt will be truncated
                    if it exceeds the maximum allowed prompt size.
        """
        client = self._get_client()
        sys_len = len(self.system_prompt) if self.system_prompt else 0
        user_prompt_max_len = self.profile.llm_max_prompt_size - sys_len - len(config.LITELLM_CLIENT.TRUNCATION_MSG)
        if user_prompt_max_len <= 0:
            raise ValueError(
                f"System prompt length ({sys_len}) exceeds max prompt size ({self.profile.llm_max_prompt_size})."
            )
        original_len = len(prompt)
        if len(prompt) > user_prompt_max_len:
            half = int(user_prompt_max_len / 2)
            prompt = prompt[:half] + config.LITELLM_CLIENT.TRUNCATION_MSG + prompt[-half:]
            logger.warning(f"User prompt truncated. original={original_len} truncated={len(prompt)}")
        messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        common_params = {
            "messages": messages,
            "model": self.profile.model_name,
            "temperature": self.profile.temperature,
            "top_p": self.profile.top_p,
            "max_completion_tokens": self.profile.max_tokens,
            "reasoning_effort": self.profile.reasoning_effort,
            "response_format": self.response_format,
        }
        if self.response_format:
            response = await client.beta.chat.completions.parse(**common_params)
            return response.choices[0].message.parsed
        response = await client.chat.completions.create(**common_params)
        return response.choices[0].message.content.strip()

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
                prompt=prompt,
            )
        )
