"""Environment settings loaded from env vars or .env files."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ThrottleConfig(BaseModel):
    """Per-model concurrency + rate-limit config.

    MAX_CONCURRENT: max in-flight requests (semaphore size).
    RATE_PER_MINUTE: token-bucket rate limit.  0 = disabled (self-hosted default).
    """

    MAX_CONCURRENT: int = 10
    RATE_PER_MINUTE: int = 0


class Settings(BaseSettings):
    """Strict environment settings. All fields are required unless defaults are set."""

    # --- LiteLLM proxy ---
    LITELLM_BASE_URL: str = Field(min_length=1)
    LITELLM_MASTER_KEY: SecretStr = Field(min_length=1)

    DMS_BASE_URL: str = Field(min_length=1)
    VLLM_MODEL: str = Field(min_length=1)
    METADATA_MODEL_NAME: str = Field(min_length=1)
    STRUCTURE_MODEL_NAME: str = Field(min_length=1)
    STRUCTURE_NODE_MAX_NODE_CHARS: int = Field(default=128_000, ge=1)
    SCHWERPUNKTTHEMA_MODEL_NAME: str = Field(min_length=1)
    SUMMARIZATION_MODEL_NAME: str = Field(min_length=1)
    VLM_SUMMARY_MODEL_NAME: str = Field(min_length=1)
    TEMPORAL_SERVER_URL: str = Field(min_length=1)
    TEMPORAL_TASK_QUEUE: str = Field(min_length=1)
    TEMPORAL_S3_BUCKET_NAME: str = Field(min_length=1)
    TEMPORAL_S3_ENDPOINT_URL: str = Field(min_length=1)
    TEMPORAL_S3_ACCESS_KEY_ID: SecretStr = Field(min_length=1)
    TEMPORAL_S3_SECRET_ACCESS_KEY: SecretStr = Field(min_length=1)
    TEMPORAL_S3_REGION: str = Field(min_length=1)
    OTEL_SERVICE_NAME: str = Field(min_length=1)
    OTEL_ENDPOINT: str = Field(min_length=1)
    UNO_HOST: str = Field(min_length=1)
    UNO_PORT: int = Field(ge=1, le=65535)
    UNO_PROTOCOL: str = Field(min_length=1)
    SINGLE_DOCUMENT_WORKFLOW_CONCURRENCY: int = Field(ge=1)

    THROTTLE_GLOBAL: ThrottleConfig
    THROTTLE_VLM: ThrottleConfig
    THROTTLE_VLM_SUMMARY: ThrottleConfig
    THROTTLE_SUMMARIZATION: ThrottleConfig
    THROTTLE_SCHWERPUNKTTHEMA: ThrottleConfig
    THROTTLE_METADATA: ThrottleConfig
    THROTTLE_HYPOTHETICAL_QUESTIONS: ThrottleConfig
    THROTTLE_SPECIES_SCALE: ThrottleConfig
    THROTTLE_STRUCTURE: ThrottleConfig = ThrottleConfig()
    THROTTLE_EMBEDDING: ThrottleConfig = ThrottleConfig()

    EXTRACTION_PROVIDER: str = Field(default="docling", min_length=1)
    EXTRACTION_CHUNK_CONCURRENCY: int = Field(default=1, ge=1)

    DOCLING_HOST: str = Field(min_length=1)
    DOCLING_PORT: int = Field(ge=1, le=65535)
    DOCLING_PROTOCOL: str = Field(default="http")
    DOCLING_OCR_ENGINE: str = Field(default="easyocr")

    QDRANT_BASE_URL: str = Field(min_length=1)
    QDRANT_API_KEY: SecretStr = Field(default="")
    QDRANT_DENSE_VECTOR_SIZE: int = Field(ge=1, le=8192)
    QDRANT_COLLECTION_NAME: str = Field(default="data", min_length=1)
    EMBEDDING_MODEL: str = Field(min_length=1)

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
    )


ENV = Settings()
