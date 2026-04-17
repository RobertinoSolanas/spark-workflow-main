"""Configuration settings for the microservice."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    SERVICE_NAME: str
    TEMPORAL_ADDRESS: str
    TEMPORAL_NAMESPACE: str

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
