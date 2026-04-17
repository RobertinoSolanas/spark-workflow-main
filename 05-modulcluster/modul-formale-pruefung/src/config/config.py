"""
Application configuration — internal defaults that do not vary between deploys.
Environment-specific settings live in env.py.
"""

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from temporalio.common import RetryPolicy

from src.config.env import ENV, LiteLLMModel


class LLMProfile(BaseModel):
    """Defines configuration parameters for a specific LLM model."""

    model_name: LiteLLMModel = Field(
        description="LLM model name as registered in the LiteLLM proxy.",
    )
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="Controls randomness (0.0 to 1.0)")
    top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: int = Field(15000, gt=0, description="Maximum tokens to generate")
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium", description="The level of reasoning effort for the model"
    )
    llm_max_prompt_size: int = Field(
        default=300000,
        description=(
            "Maximum Size of the user prompt. Larger Prompts get truncated in the "
            "middle. The system prompt length reduces the user prompt length."
        ),
    )


class InhaltsverzeichnisFinderParamsConfig(BaseModel):
    """Configuration parameters for Table of Contents extraction."""

    N_PAGE_SEARCH: int = 5
    MIN_CHUNK_LENGTH: int = 800
    LLM_PROFILE: LLMProfile = LLMProfile(
        model_name=ENV.LITELLM.MODEL,
        reasoning_effort="high",
    )
    EXTRACTION_ERROR_TOLERANCE_RATIO: float = 0.3


class LLMMatchingParamsConfig(BaseModel):
    """Configuration parameters for the LLM Matching Workflow."""

    N_PAGE_SUMMARY: int = 5
    MAX_ELEMENTS_IN_CONTEXT: int = 5
    MAX_CONCURRENT_FILES_FOR_MATCH: int = 100
    LLM_ACTIVITY_TIMEOUT_SECONDS: int = 1000
    LLM_PROFILE: LLMProfile = LLMProfile(
        model_name=ENV.LITELLM.MODEL,
        reasoning_effort="high",
    )


class TemporalConfig(BaseModel):
    """Runtime tuning for worker/activity execution."""

    LLM_MAX_CONCURRENT_ACTIVITIES: int = 390
    ACTIVITY_TIMEOUT_SECONDS: int = 60
    UPLOAD_ACTIVITY_TIMEOUT_SECONDS: int = 240
    LLM_ACTIVITY_TIMEOUT_SECONDS: int = 600
    LLM_RETRY_POLICY: RetryPolicy = RetryPolicy(
        maximum_attempts=30,
        initial_interval=timedelta(seconds=10),
        backoff_coefficient=2,
        maximum_interval=timedelta(seconds=30),
    )
    ACTIVITY_MAX_RETRIES: int = 20


class DMSConfig(BaseModel):
    """DMS pagination safeguards."""

    PAGE_SIZE: int = 500
    MAX_PAGES: int = 200


class LiteLLMClientConfig(BaseModel):
    """LLM client tuning defaults."""

    TIMEOUT_SECONDS: float = 240.0
    TRUNCATION_MSG: str = "\n... [truncated] ...\n"


class Config:
    """Central application configuration for formale-pruefung"""

    INHALTSVERZEICHNIS_FINDER = InhaltsverzeichnisFinderParamsConfig()
    LLM_MATCHING = LLMMatchingParamsConfig()
    TEMPORAL = TemporalConfig()
    DMS = DMSConfig()
    LITELLM_CLIENT = LiteLLMClientConfig()


config = Config()
