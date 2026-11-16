"""Gemini and Groq clients over plain HTTP. Keys are sent only in headers, never logged."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from lyvern.llm.base import LlmError, LlmResponse, LlmUsage
from lyvern.llm.redact import redact_secrets

_RETRY = {429, 500, 502, 503, 504}


def _provider_message(response: httpx.Response, secret: str) -> str:
    """The provider's own error text, with our key and any token-shaped strings removed."""
    try:
        data = response.json()
        message = (
            str((data.get("error") or {}).get("message") or "") if isinstance(data, dict) else ""
        )
    except ValueError:
        return ""
    if secret:
        message = message.replace(secret, "[REDACTED]")
    return redact_secrets(message)[0][:160]


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "")
    try:
        return min(60.0, max(0.0, float(value)))
    except ValueError:
        return 0.0


def _post_json(
    http: httpx.Client,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    sleep: Callable[[float], None],
    secret: str = "",
    retries: int = 2,
) -> dict[str, Any]:
    def post() -> httpx.Response:
        try:
            return http.post(url, headers=headers, json=body)
        except httpx.HTTPError as error:
            # name the failure only: the exception text can contain the request URL
            raise LlmError(f"provider request failed ({type(error).__name__})") from None

    response = post()
    for attempt in range(retries):
        if response.status_code not in _RETRY:
            break
        sleep(max(1.5 * (2**attempt), _retry_after(response)))
        response = post()
    detail = _provider_message(response, secret) if response.status_code >= 400 else ""
    suffix = f": {detail}" if detail else ""
    if response.status_code == 429:
        raise LlmError(f"provider rate limit reached (HTTP 429){suffix}")
    if response.status_code >= 400:
        raise LlmError(f"provider returned HTTP {response.status_code}{suffix}")
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
        model: str = "gemini-flash-lite-latest",
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
        data = _post_json(
            self._http, url, {"x-goog-api-key": self._key}, body, self._sleep, self._key
        )
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
        try:
            return self._call(system, user, max_output_tokens, strict_json=True)
        except LlmError as error:
            # Groq's strict JSON mode rejects some outputs with HTTP 400 ("Failed to generate
            # JSON"). Retry once without it; our own validation is the real judge of the output.
            if "HTTP 400" in str(error) and "JSON" in str(error):
                return self._call(system, user, max_output_tokens, strict_json=False)
            raise

    def _call(
        self, system: str, user: str, max_output_tokens: int, *, strict_json: bool
    ) -> LlmResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_output_tokens,
        }
        if strict_json:
            body["response_format"] = {"type": "json_object"}
        data = _post_json(
            self._http,
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {self._key}"},
            body,
            self._sleep,
            self._key,
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
