# src/models/llm_client.py
"""
LLM Client module for creating AsyncOpenAI clients used with Instructor.

All requests are routed through the shared LiteLLM proxy
(single base URL + master key).
"""

import httpx
from openai import AsyncOpenAI

from src.env import ENV


def _resolve_model_name(model_type: str) -> str:
    """Return the env-configured model name for a given model type."""
    if model_type == "metadata":
        return ENV.METADATA_MODEL_NAME
    if model_type == "schwerpunktthema":
        return ENV.SCHWERPUNKTTHEMA_MODEL_NAME
    if model_type == "summarization":
        return ENV.SUMMARIZATION_MODEL_NAME
    if model_type == "vlm_summary":
        return ENV.VLM_SUMMARY_MODEL_NAME
    if model_type == "structure":
        return ENV.STRUCTURE_MODEL_NAME
    raise ValueError(f"Unknown model type: {model_type}")


async def get_openai_client(model_type: str) -> tuple[AsyncOpenAI, str]:
    """
    Get an AsyncOpenAI client for the specified model type.

    Returns a tuple of (client, model_name) for use with Instructor.
    All requests go through the LiteLLM proxy.

    Args:
        model_type: One of "metadata", "schwerpunktthema", "summarization", "vlm_summary", "structure"

    Returns:
        Tuple of (AsyncOpenAI client, model name string)
    """
    model_name = _resolve_model_name(model_type)

    client = AsyncOpenAI(
        base_url=ENV.LITELLM_BASE_URL,
        api_key=ENV.LITELLM_MASTER_KEY.get_secret_value(),
        timeout=300.0,
        http_client=httpx.AsyncClient(
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            timeout=httpx.Timeout(300.0),
        ),
    )
    return client, model_name
