"""Configuration settings for the microservice."""

import os

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalSettings(BaseModel):
    HOST: str
    TASK_QUEUE: str
    NAMESPACE: str
    ENABLE_APPROVAL: bool
    APPROVAL_TIMEOUT_DAYS: int


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    SERVICE_NAME: str

    # Middleware Setup
    CORS_ORIGINS: str | list[str]
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

    # S3 Storage Config
    BUCKET_NAME: str
    DOC_STORE_PATH: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_EXTERNAL_URL: str
    S3_ENDPOINT_URL: str
    S3_REGION: str | None = None

    # Retention period for Temporal data
    CHECKPOINT_RETENTION_PERIOD_DAYS: int

    # File upload configuration
    ALLOWED_FILE_TYPES: set[str] = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
        "application/zip",
        "application/json",
        "text/markdown",
    }

    # File extensions mapped to MIME types for validation
    ALLOWED_FILE_EXTENSIONS: dict[str, str] = {
        ".zip": "application/zip",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".json": "application/json",
        ".md": "text/markdown",
    }

    ALLOWED_HTTP_METHODS: list[str] = [
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        """Parses a comma-separated string of CORS origins into a list.

        This validator is used to convert the CORS_ORIGINS environment
        variable or config value into a list of origin strings. It trims whitespace
        and ignores empty values.

        Args:
            v (str | list[str]): A comma-separated string of origins
                (e.g., "http://localhost, https://example.com") or a list.

        Returns:
            list[str]: A list of cleaned and non-empty origin strings.
        """
        if isinstance(v, list):
            return v
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    TEMPORAL: TemporalSettings

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        case_sensitive=True,
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
    )


settings = Settings()  # type: ignore
