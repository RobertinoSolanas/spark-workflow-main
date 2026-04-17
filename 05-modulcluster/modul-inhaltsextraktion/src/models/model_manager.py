# src/models/model_manager.py
"""
Type definitions for LLM configurations used by activities.
"""

from typing import Literal, TypedDict


class SelfHostedConfig(TypedDict):
    """Configuration for a self-hosted LLM."""

    provider: Literal["self_hosted"]
    model_name: Literal["metadata", "schwerpunktthema", "summarization", "vlm_summary", "structure"]


LLMConfig = SelfHostedConfig
