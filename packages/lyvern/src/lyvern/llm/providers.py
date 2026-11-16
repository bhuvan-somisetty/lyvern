"""Gemini and Groq clients over plain HTTP. Keys are sent only in headers, never logged."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from lyvern.llm.base import LlmError, LlmResponse, LlmUsage

_RETRY = {429, 500, 502, 503, 504}


def _post_json(
    http: httpx.Client,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    sleep: Callable[[float], None],
    retries: int = 2,
) -> dict[str, Any]:
    response = http.post(url, headers=headers, json=body)
    for attempt in range(retries):
        if response.status_code not in _RETRY:
            break
        sleep(1.5 * (2**attempt))
        response = http.post(url, headers=headers, json=body)
    if response.status_code == 429:
        raise LlmError("provider rate limit reached (HTTP 429)")
    if response.status_code >= 400:
        raise LlmError(f"provider returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as error:
        raise LlmError("provider returned a non-JSON response") from error
    if not isinstance(data, dict):
        raise LlmError("provider returned an unexpected response")
    return data


class GeminiClient:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-latest",
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise LlmError("no Gemini API key configured")
        self._key = api_key
        self.model = model
        self._sleep = sleep
        self._http = httpx.Client(transport=transport, timeout=90.0)

    def complete(self, system: str, user: str, *, max_output_tokens: int = 2048) -> LlmResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        data = _post_json(self._http, url, {"x-goog-api-key": self._key}, body, self._sleep)
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError("Gemini returned no usable candidate") from error
        usage = data.get("usageMetadata") or {}
        return LlmResponse(
            text=text,
            usage=LlmUsage(usage.get("promptTokenCount"), usage.get("candidatesTokenCount")),
            model=self.model,
        )


class GroqClient:
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise LlmError("no Groq API key configured")
        self._key = api_key
        self.model = model
        self._sleep = sleep
        self._http = httpx.Client(transport=transport, timeout=90.0)

    def complete(self, system: str, user: str, *, max_output_tokens: int = 2048) -> LlmResponse:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        data = _post_json(
            self._http,
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {self._key}"},
            body,
            self._sleep,
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError("Groq returned no usable choice") from error
        usage = data.get("usage") or {}
        return LlmResponse(
            text=text,
            usage=LlmUsage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
            model=self.model,
        )
