"""Application settings, read from environment variables (prefix PRINTEL_) or a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRINTEL_", env_file=".env", extra="ignore")

    # Single place for the product name. The final brand is not chosen yet.
    product_name: str = "pr-intel"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://printel:printel@localhost:5433/printel")
    )
    redis_url: SecretStr = Field(default=SecretStr("redis://localhost:6380/0"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
