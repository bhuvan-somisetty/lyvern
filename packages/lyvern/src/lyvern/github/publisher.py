"""Publish a review to GitHub through the pull request review API.

Safety rules enforced here:

* ``WriteGuard``: nothing is ever sent for a repository that is not on the owner's
  allowlist. The check happens before any network call.
* One review is created with an explicit ``event`` (COMMENT, REQUEST_CHANGES, APPROVE).
  An approval is never simulated with a normal comment: if GitHub refuses an APPROVE it
  is downgraded to COMMENT, and the result and the review body say so.
* Inline comments already posted by an earlier run (matched by their hidden fingerprint
  marker) are skipped. If GitHub rejects an inline location, the comments are moved into
  the review body instead of being lost or retried blindly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from lyvern.engine.contracts import ReviewEvent
from lyvern.engine.render import extract_fingerprints

API = "https://api.github.com"
MAX_COMMENT_PAGES = 10


class WriteNotAllowed(PermissionError):
    """The repository is not on the write allowlist."""


class PublishError(RuntimeError):
    pass


class WriteGuard:
    def __init__(self, allowed: Sequence[str]) -> None:
        self._allowed = frozenset(item.strip().lower() for item in allowed if item.strip())

    @classmethod
    def from_setting(cls, value: str) -> WriteGuard:
        return cls(value.split(","))

    def assert_allowed(self, repo_full_name: str) -> None:
        if repo_full_name.strip().lower() not in self._allowed:
            raise WriteNotAllowed(
                f"writing to {repo_full_name} is not allowed (write allowlist: "
                f"{sorted(self._allowed) or 'empty'})"
            )


@dataclass(frozen=True)
class ReviewComment:
    path: str
    line: int
    body: str
    start_line: int | None = None
    side: str = "RIGHT"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "line": self.line,
            "side": self.side,
            "body": self.body,
        }
        if self.start_line is not None and self.start_line < self.line:
            payload["start_line"] = self.start_line
            payload["start_side"] = self.side
        return payload


@dataclass(frozen=True)
class PublishResult:
    review_id: int | None
    event_requested: ReviewEvent
    event_posted: ReviewEvent
    inline_posted: int
    inline_skipped_duplicates: int
    inline_moved_to_body: int
    notes: tuple[str, ...]


class GitHubPublisher:
    def __init__(
        self,
        guard: WriteGuard,
        token_provider: Callable[[], str],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._guard = guard
        self._token = token_provider
        self._http = httpx.Client(base_url=API, transport=transport, timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def existing_fingerprints(self, repo: str, pr_number: int) -> set[str]:
        self._guard.assert_allowed(repo)
        found: set[str] = set()
        for page in range(1, MAX_COMMENT_PAGES + 1):
            response = self._http.get(
                f"/repos/{repo}/pulls/{pr_number}/comments",
                params={"per_page": 100, "page": page},
                headers=self._headers(),
            )
            if response.status_code != 200:
                raise PublishError(
                    f"could not list existing comments (HTTP {response.status_code})"
                )
            batch = response.json()
            for item in batch:
                found |= extract_fingerprints(str(item.get("body") or ""))
            if len(batch) < 100:
                break
        return found

    def dismiss_review(self, repo: str, pr_number: int, review_id: int, message: str) -> bool:
        """Dismiss one of OUR earlier reviews; False if GitHub refuses (e.g. already dismissed)."""
        self._guard.assert_allowed(repo)
        response = self._http.put(
            f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
            json={"message": message},
            headers=self._headers(),
        )
        return response.status_code == 200

    def _post_review(self, repo: str, pr_number: int, payload: dict[str, Any]) -> httpx.Response:
        return self._http.post(
            f"/repos/{repo}/pulls/{pr_number}/reviews", json=payload, headers=self._headers()
        )

    def publish_review(
        self,
        repo: str,
        pr_number: int,
        head_sha: str,
        event: ReviewEvent,
        body: str,
        comments: Sequence[ReviewComment],
    ) -> PublishResult:
        self._guard.assert_allowed(repo)  # before any network call
        notes: list[str] = []

        known = self.existing_fingerprints(repo, pr_number)
        fresh = [c for c in comments if not (extract_fingerprints(c.body) & known)]
        skipped = len(comments) - len(fresh)
        if skipped:
            notes.append(
                f"{skipped} inline comment(s) already posted by an earlier run were skipped"
            )

        posted_event = event
        inline = list(fresh)
        review_body = body
        moved = 0

        for _attempt in range(3):
            payload: dict[str, Any] = {
                "commit_id": head_sha,
                "body": review_body,
                "event": posted_event.value,
            }
            if inline:
                payload["comments"] = [c.to_payload() for c in inline]
            response = self._post_review(repo, pr_number, payload)
            if response.status_code == 200:
                review_id = response.json().get("id")
                return PublishResult(
                    review_id=int(review_id) if review_id is not None else None,
                    event_requested=event,
                    event_posted=posted_event,
                    inline_posted=len(inline),
                    inline_skipped_duplicates=skipped,
                    inline_moved_to_body=moved,
                    notes=tuple(notes),
                )
            if response.status_code != 422:
                raise PublishError(f"GitHub refused the review (HTTP {response.status_code})")

            detail = response.text.lower()
            if posted_event == ReviewEvent.APPROVE and "approve" in detail:
                posted_event = ReviewEvent.COMMENT
                review_body += (
                    "\n\nAutomated approval was not accepted by GitHub for this pull request "
                    "(branch rules or ownership), so this review is a comment only."
                )
                notes.append("APPROVE refused by GitHub; downgraded to COMMENT")
                continue
            if inline:
                moved = len(inline)
                review_body += (
                    "\n\nInline comments that GitHub could not attach to the diff:\n\n"
                    + ("\n\n".join(f"`{c.path}:{c.line}`\n{c.body}" for c in inline))
                )
                inline = []
                notes.append(
                    "GitHub rejected inline locations; comments moved into the review body"
                )
                continue
            raise PublishError(f"GitHub rejected the review: {response.text[:300]}")
        raise PublishError("review could not be published after retries")
