"""GitHub App authentication: a short-lived JWT, exchanged for installation tokens.

Tokens live only in memory. They are never logged and never written to disk.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import jwt

API = "https://api.github.com"
REFRESH_MARGIN_SECONDS = 120


class AppAuthError(RuntimeError):
    pass


class AppAuth:
    def __init__(
        self,
        app_id: str,
        private_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not app_id or not private_key:
            raise AppAuthError("GitHub App id and private key are required")
        self._app_id = app_id
        self._key = private_key
        self._clock = clock
        self._http = httpx.Client(base_url=API, transport=transport, timeout=30.0)
        self._cache: dict[int, tuple[str, float]] = {}

    @classmethod
    def from_key_file(cls, app_id: str, key_path: str, **kwargs: object) -> AppAuth:
        return cls(app_id, Path(key_path).read_text(encoding="utf-8"), **kwargs)  # type: ignore[arg-type]

    def app_jwt(self) -> str:
        now = int(self._clock())
        claims = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}
        return jwt.encode(claims, self._key, algorithm="RS256")

    def installation_token(self, installation_id: int) -> str:
        cached = self._cache.get(installation_id)
        if cached and cached[1] - self._clock() > REFRESH_MARGIN_SECONDS:
            return cached[0]
        response = self._http.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {self.app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if response.status_code != 201:
            raise AppAuthError(
                f"could not create an installation token (HTTP {response.status_code})"
            )
        data = response.json()
        expires = datetime.fromisoformat(str(data["expires_at"])).timestamp()
        self._cache[installation_id] = (str(data["token"]), expires)
        return str(data["token"])

    def close(self) -> None:
        self._http.close()
