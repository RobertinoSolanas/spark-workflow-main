"""Configuration settings for the microservice."""

import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    SERVICE_NAME: str

    # Middleware Setup
    PROJECT_LOGIC_SERVICE_CORS_ORIGINS: str | list[str]
    BLOCKED_HTTP_METHODS: set[str] = {
        "TRACE",
        "PUT",
    }

    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    ALLOWED_HTTP_METHODS: list[str] = [
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]

    @field_validator("PROJECT_LOGIC_SERVICE_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
