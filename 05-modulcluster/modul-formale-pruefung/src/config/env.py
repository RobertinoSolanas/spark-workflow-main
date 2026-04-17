"""Environment settings loaded from env vars or .env files."""

import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LiteLLMModel = Literal[
    "mistral-small-24b-instruct",
    "gpt-oss-120b",
]


class LiteLLMConfig(BaseModel):
    """LiteLLM API settings."""

    BASE_URL: str = Field(min_length=1)
    MASTER_KEY: str = Field(min_length=1)
    MODEL: LiteLLMModel = Field(min_length=1)


class TemporalConfig(BaseModel):
    """Temporal and Temporal S3 settings."""

    HOST: str = Field(min_length=1)
    TASK_QUEUE: str = Field(min_length=1)
    LLM_MAX_PER_SECOND: int = Field(gt=0)
    S3_BUCKET_NAME: str = Field(min_length=1)
    S3_ENDPOINT_URL: str = Field(min_length=1)
    S3_ACCESS_KEY_ID: str = Field(min_length=1)
    S3_SECRET_ACCESS_KEY: str = Field(min_length=1)
    S3_REGION: str


class Settings(BaseSettings):
    """Strict environment settings. All fields are required unless defaults are set."""

    LITELLM: LiteLLMConfig
    DMS_BASE_URL: str = Field(min_length=1)
    OTEL_SERVICE_NAME: str = Field(min_length=1)
    OTEL_ENDPOINT: str = Field(min_length=1)
    TEMPORAL: TemporalConfig

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
        case_sensitive=True,
    )


ENV = Settings()
