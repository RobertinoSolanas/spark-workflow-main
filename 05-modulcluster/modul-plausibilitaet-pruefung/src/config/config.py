"""
Application configuration — internal defaults that do not vary between deploys.
Environment-specific settings live in env.py.
"""

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from temporalio.common import RetryPolicy

from src.config.env import LiteLLMModel


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


class RiskScreeningParamsConfig(BaseModel):
    """Configuration parameters for the risk screening workflow."""

    K_TOTAL_COMPARISON_CLAIMS: int = 10
    RATING_THRESHOLD: int = 50
    K_LOCAL_COMPARISON_CLAIMS: int = 1
    K_ERLAEUTERUNGSBERICHT_COMPARISON_CLAIMS: int = 4
    QDRANT_QUERY_BATCH_SIZE: int = 50


class ContextCheckingParamsConfig(BaseModel):
    """Configuration parameters for the context checking workflow."""

    MAX_PREVIOUS_CHUNKS: int = 10
    MAX_PREVIOUS_TEXT_CHARS: int = 5000
    MAX_FOLLOWUP_CHUNKS: int = 1
    MAX_FOLLOWUP_TEXT_CHARS: int = 500
    PREVIOUS_TEXT_TRUNCATE_RATIO: float = 0.2
    RATING_THRESHOLD: int = 50
    LLM_SUMMARY_BEGIN_MARKER: str = "<<<BEGIN_LLM_SUMMARY_NON_VERBATIM>>>"
    LLM_SUMMARY_END_MARKER: str = "<<<END_LLM_SUMMARY_NON_VERBATIM>>>"


class SummarizingParamsConfig(BaseModel):
    """Configuration parameters for the summarizing workflow."""

    MAX_EDGES_PER_CLUSTER: int = 5
    SIMILARITY_THRESHOLD: float = Field(
        0.80,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for merging two inconsistency pairs into one cluster.",
    )


class QdrantBuilderParamsConfig(BaseModel):
    """Configuration parameters for the Qdrant builder workflow."""

    DEFAULT_ACTIVITY_RETRIES: int = 5
    ACTIVITY_TIMEOUT_SECONDS: int = 10000
    PROCESS_AND_UPLOAD_BATCH_SIZE: int = 50
    CHUNK_MIN_LENGTH: int = 50
    TABLE_ROW_BATCH_SIZE: int = 5


class TemporalConfig(BaseModel):
    """Runtime tuning for worker/activity execution."""

    MAX_PENDING_ACTIVITIES: int = 900
    LLM_MAX_CONCURRENT_ACTIVITIES: int = 390
    ACTIVITY_TIMEOUT_SECONDS: int = 600
    UPLOAD_ACTIVITY_TIMEOUT_SECONDS: int = 600
    LLM_ACTIVITY_TIMEOUT_SECONDS: int = 600
    ACTIVITY_MAX_RETRIES: int = 20
    LLM_RETRY_POLICY: RetryPolicy = RetryPolicy(
        maximum_attempts=30,
        initial_interval=timedelta(seconds=10),
        backoff_coefficient=2,
        maximum_interval=timedelta(seconds=30),
    )


class LiteLLMClientConfig(BaseModel):
    """Internal client tuning for LiteLLM/OpenAI SDK calls."""

    TIMEOUT_SECONDS: float = 600.0
    MAX_RETRIES: int = 3


class DMSConfig(BaseModel):
    """DMS pagination safeguards."""

    PAGE_SIZE: int = 500
    MAX_PAGES: int = 200


class EmbeddingConfig(BaseModel):
    """Embedding/vector storage settings."""

    UPLOAD_BATCH_SIZE: int = 1000
    TIMEOUT_SECONDS: int = 180
    MAX_RETRIES: int = 3
    RETRY_INTERVAL_SECONDS: float = 10.0


class QdrantConfig(BaseModel):
    """Qdrant-specific configuration parameters."""

    CLAIM_COLLECTION_NAME: str = "plausibility"
    DATA_COLLECTION_NAME: str = "data"
    INDEX_KEYWORDS: list[str] = ["project_id", "document_id", "chunk_id", "claim_metadata.claim_id"]
    INDEX_TEXT: list[str] = ["title", "claim_metadata.claim_content"]
    INDEX_BOOLS: list[str] = ["erlauterungsbericht"]


class Config:
    """Global configuration object with all default settings."""

    # Qdrant builder workflow settings
    QDRANT_BUILDER = QdrantBuilderParamsConfig()
    EMBEDDING = EmbeddingConfig()

    # Check logic workflow settings
    RISK_SCREENING = RiskScreeningParamsConfig()
    CONTEXT_CHECKING = ContextCheckingParamsConfig()
    SUMMARIZING = SummarizingParamsConfig()

    # Orchestration/service settings
    TEMPORAL = TemporalConfig()
    LITELLM_CLIENT = LiteLLMClientConfig()
    DMS = DMSConfig()
    QDRANT = QdrantConfig()
    LLM_TASK_QUEUE_SUFFIX = "-llm"


config = Config()
