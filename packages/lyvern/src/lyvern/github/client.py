"""Read-only GitHub client.

Safety by construction: the only network primitive is ``_get`` and it can only send
GET requests. There is no method that creates, edits or deletes anything on GitHub,
so reviewer mode cannot post a comment on a pull request in someone else's project,
even by mistake. A unit test fails the build if a write-capable method is ever added.
"""

from __future__ import annotations

import base64
import binascii
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef

API = "https://api.github.com"
MAX_FILE_PAGES = 30  # GitHub lists at most 3000 files per pull request (100 per page)
MAX_CONTENT_BYTES = 500_000
_RETRY_STATUS = {502, 503, 504}


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status


class GitHubRateLimited(GitHubError):
    def __init__(self, reset_epoch: int | None) -> None:
        super().__init__(403, "rate limit exceeded")
        self.reset_epoch = reset_epoch


class GitHubReadClient:
    def __init__(
        self,
        token: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lyvern-reviewer-mode",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=API,
            headers=headers,
            transport=transport,
            timeout=30.0,
            follow_redirects=False,
        )
        self._sleep = sleep
        self._max_retries = max_retries

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ primitive

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._http.get(path, params=params)
        for attempt in range(self._max_retries):
            if response.status_code not in _RETRY_STATUS:
                break
            self._sleep(0.5 * (2**attempt))
            response = self._http.get(path, params=params)
        limited = response.headers.get("x-ratelimit-remaining") == "0"
        if response.status_code in (403, 429) and limited:
            reset = response.headers.get("x-ratelimit-reset")
            raise GitHubRateLimited(int(reset) if reset and reset.isdigit() else None)
        if response.status_code >= 400:
            try:
                message = str(response.json().get("message", ""))
            except ValueError:
                message = response.text[:200]
            raise GitHubError(response.status_code, message)
        return response.json()

    # --------------------------------------------------------------------- reads

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        data = self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}")
        head_repo = (data["head"].get("repo") or {}).get("full_name") or f"{ref.owner}/{ref.repo}"
        return PullRequestInfo(
            owner=ref.owner,
            repo=ref.repo,
            number=ref.number,
            title=data.get("title") or "",
            body=data.get("body") or "",
            author=(data.get("user") or {}).get("login") or "",
            state=data["state"],
            draft=bool(data.get("draft")),
            html_url=data["html_url"],
            base_ref=data["base"]["ref"],
            base_sha=data["base"]["sha"],
            head_ref=data["head"]["ref"],
            head_sha=data["head"]["sha"],
            head_repo_full_name=head_repo,
            changed_files=int(data.get("changed_files") or 0),
            additions=int(data.get("additions") or 0),
            deletions=int(data.get("deletions") or 0),
        )

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        files: list[ChangedFileInfo] = []
        for page in range(1, MAX_FILE_PAGES + 1):
            batch = self._get(
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files",
                {"per_page": 100, "page": page},
            )
            files.extend(ChangedFileInfo.model_validate(item) for item in batch)
            if len(batch) < 100:
                break
        return files

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        """Return the file's text at ``ref``; None if missing, binary, too big or undecodable."""
        try:
            data = self._get(
                f"/repos/{repo_full_name}/contents/{quote(path, safe='/')}", {"ref": ref}
            )
        except GitHubError as error:
            if error.status == 404:
                return None
            raise
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            return None
        if int(data.get("size") or 0) > MAX_CONTENT_BYTES:
            return None
        try:
            raw = base64.b64decode(data.get("content") or "", validate=False)
            return raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
