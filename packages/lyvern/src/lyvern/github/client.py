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

from lyvern.github.models import (
    ChangedFileInfo,
    MergeState,
    PullRequestInfo,
    ReviewCommentInfo,
    ReviewInfo,
)
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
        return self._pr_info(ref, self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"))

    def list_open_pull_requests(
        self, owner: str, repo: str, base: str, *, limit: int = 50
    ) -> list[PullRequestInfo]:
        """Open pull requests whose target branch is ``base`` (bounded, newest first)."""
        found: list[PullRequestInfo] = []
        page = 1
        while len(found) < limit:
            batch = self._get(
                f"/repos/{owner}/{repo}/pulls",
                {"state": "open", "base": base, "sort": "updated", "per_page": 50, "page": page},
            )
            for item in batch:
                ref = PullRequestRef(owner, repo, int(item["number"]))
                found.append(self._pr_info(ref, item))
            if len(batch) < 50:
                break
            page += 1
        return found[:limit]

    def list_pull_requests(
        self, owner: str, repo: str, *, state: str = "closed", limit: int = 100, start_page: int = 1
    ) -> list[PullRequestInfo]:
        """Pull requests of a repository, newest first (bounded)."""
        found: list[PullRequestInfo] = []
        page = start_page
        while len(found) < limit:
            batch = self._get(
                f"/repos/{owner}/{repo}/pulls",
                {
                    "state": state,
                    "sort": "created",
                    "direction": "desc",
                    "per_page": 50,
                    "page": page,
                },
            )
            for item in batch:
                ref = PullRequestRef(owner, repo, int(item["number"]))
                found.append(self._pr_info(ref, item))
            if len(batch) < 50:
                break
            page += 1
        return found[:limit]

    def list_reviews(self, ref: PullRequestRef) -> list[ReviewInfo]:
        reviews: list[ReviewInfo] = []
        for page in range(1, 6):
            batch = self._get(
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/reviews",
                {"per_page": 100, "page": page},
            )
            for item in batch:
                user = item.get("user") or {}
                reviews.append(
                    ReviewInfo(
                        state=str(item.get("state") or ""),
                        author=str(user.get("login") or ""),
                        author_type=str(user.get("type") or ""),
                        submitted_at=str(item.get("submitted_at") or ""),
                    )
                )
            if len(batch) < 100:
                break
        return reviews

    @staticmethod
    def _pr_info(ref: PullRequestRef, data: dict[str, Any]) -> PullRequestInfo:
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
            author_association=str(data.get("author_association") or ""),
            created_at=str(data.get("created_at") or ""),
            merged=bool(data.get("merged_at")),
        )

    def get_merge_state(
        self,
        ref: PullRequestRef,
        *,
        attempts: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> MergeState:
        """GitHub computes mergeability in the background: ask again while it says unknown."""
        state = MergeState(mergeable=None, state="unknown")
        for attempt in range(attempts):
            data = self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}")
            mergeable = data.get("mergeable")
            state = MergeState(
                mergeable=mergeable if isinstance(mergeable, bool) else None,
                state=str(data.get("mergeable_state") or "unknown"),
            )
            if state.mergeable is not None:
                break
            if attempt < attempts - 1:
                sleep(1.5 * (attempt + 1))
        return state

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

    def list_review_comments(self, ref: PullRequestRef) -> list[ReviewCommentInfo]:
        """Inline review comments already written on the pull request (read-only)."""
        out: list[ReviewCommentInfo] = []
        for page in range(1, MAX_FILE_PAGES + 1):
            batch = self._get(
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/comments",
                {"per_page": 100, "page": page},
            )
            for item in batch:
                user = item.get("user") or {}
                out.append(
                    ReviewCommentInfo(
                        path=item.get("path") or "",
                        body=item.get("body") or "",
                        author=user.get("login") or "",
                        author_type=user.get("type") or "",
                        line=item.get("line"),
                        original_line=item.get("original_line"),
                        in_reply_to_id=item.get("in_reply_to_id"),
                    )
                )
            if len(batch) < 100:
                break
        return out

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
