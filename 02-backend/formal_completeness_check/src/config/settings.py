"""Configuration settings for the microservice."""

import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    SERVICE_NAME: str
    DOCUMENT_MANAGEMENT_SERVICE_URL: str
    PROJECT_LOGIC_SERVICE_URL: str

    CORS_ORIGINS: str | list[str]
    ALLOWED_HTTP_METHODS: list[str] = [
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]

    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        """Parses a comma-separated string of CORS origins into a list."""
        if isinstance(v, list):
            return [origin.strip() for origin in v if origin.strip()]
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
