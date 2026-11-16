"""Build the optional AI reviewer from settings. Off unless a provider is named."""

from __future__ import annotations

from lyvern.config import Settings, get_settings
from lyvern.engine.llm_review import LlmReviewer
from lyvern.llm.base import LlmError
from lyvern.llm.providers import GeminiClient, GroqClient

PROVIDERS = ("gemini", "groq")


def make_llm_reviewer(provider: str | None, settings: Settings | None = None) -> LlmReviewer | None:
    name = (provider or "").strip().lower()
    if not name:
        return None
    cfg = settings or get_settings()
    if name == "gemini":
        key = cfg.gemini_api_key.get_secret_value() if cfg.gemini_api_key else ""
        return LlmReviewer(GeminiClient(key, cfg.llm_model or "gemini-flash-lite-latest"))
    if name == "groq":
        key = cfg.groq_api_key.get_secret_value() if cfg.groq_api_key else ""
        return LlmReviewer(GroqClient(key, cfg.llm_model or "openai/gpt-oss-120b"))
    raise LlmError(f"unknown LLM provider {name!r} (choose one of {', '.join(PROVIDERS)})")
