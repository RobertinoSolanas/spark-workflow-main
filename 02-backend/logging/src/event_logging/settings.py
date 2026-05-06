from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict()

    ecs_version: str = Field(
        default="8.11.0",
        description="Version of the Elastic Common Schema specification",
    )
    env: Environment | str = Field(
        default=Environment.PRODUCTION,
        validation_alias="ENV",
    )

    @property
    def pretty_print(self) -> bool:
        """Enable pretty print for development environments."""
        return self.env in (Environment.DEVELOPMENT, "development", "dev")

