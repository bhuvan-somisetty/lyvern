"""Application settings, read from environment variables (prefix LYVERN_) or a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LYVERN_", env_file=".env", extra="ignore")

    # Single place for the product name.
    product_name: str = "Lyvern"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://lyvern:lyvern@localhost:5433/lyvern")
    )
    redis_url: SecretStr = Field(default=SecretStr("redis://localhost:6380/0"))

    # --- GitHub App (ids are not secret; the key file stays outside the repository)
    github_app_id: str | None = None
    github_app_client_id: str | None = None
    github_app_private_key_path: str | None = None
    github_installation_id: int | None = None
    github_webhook_secret: SecretStr | None = None
    # Repositories the bot may WRITE to (reviews, comments). Everything else is read-only.
    write_allowed_repos: str = "bhuvan-somisetty/lyvern-sandbox"

    # Bearer token for the read-only dashboard API. Unset = the API answers 503 (locked).
    api_token: SecretStr | None = None

    # --- LLM providers (free tiers); only used by the LLM layer
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    # Which provider the review job uses for AI observations ('' = off) and an optional model.
    llm_provider: str = ""
    llm_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
