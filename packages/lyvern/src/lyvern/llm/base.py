from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LlmError(RuntimeError):
    """The provider failed or returned something unusable. Never contains keys or prompt text."""


@dataclass(frozen=True)
class LlmUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class LlmResponse:
    text: str
    usage: LlmUsage
    model: str


class LlmClient(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, max_output_tokens: int = 2048) -> LlmResponse: ...
