import os

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalSettings(BaseModel):
    host: str
    task_queue: str
    namespace: str = "default"


class APISettings(BaseModel):
    timeout: int = 10 * 60
    fvp_base_url: str
    dms_base_url: str
    plausibility_notes_base_url: str


class Settings(BaseSettings):
    CORS_ORIGINS: str | list[str]
    ALLOWED_HTTP_METHODS: list[str] = [
        "GET",
        "POST",
        "PATCH",
        "OPTIONS",
    ]

    SERVICE_NAME: str = "agent_orchestration"
    OTEL_SERVICE_NAME: str = Field(min_length=1)
    OTEL_ENDPOINT: str = Field(min_length=1)

    # Chunked uploads only work with Ceph
    USE_TRANSFER_ENCODING_CHUNKED: bool

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    temporal: TemporalSettings
    api: APISettings

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"] if not os.getenv("SKIP_DOTENV") else None,
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
    )


settings = Settings()
