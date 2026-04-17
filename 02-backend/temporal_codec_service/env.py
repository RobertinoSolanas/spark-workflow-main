"""Environment settings loaded from env vars or .env files."""

from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strict environment settings. All fields are required."""

    TEMPORAL_S3_BUCKET_NAME: str = Field(min_length=1)
    TEMPORAL_S3_ENDPOINT_URL: str = Field(min_length=1)
    TEMPORAL_S3_ACCESS_KEY_ID: str = Field(min_length=1)
    TEMPORAL_S3_SECRET_ACCESS_KEY: str = Field(min_length=1)
    TEMPORAL_S3_REGION: str = Field(min_length=1)

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        extra="ignore",
    )


ENV = Settings()
