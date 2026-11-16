"""GitHub webhook verification and parsing.

The signature is checked over the RAW request body with HMAC-SHA256 and compared in
constant time, before anything is parsed. Payload content is untrusted: only the few
fields we need are extracted and validated.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

# pull_request actions that should start (or restart) a review
REVIEW_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


class InvalidWebhook(ValueError):
    pass


def compute_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """True only if ``header`` is the correct ``sha256=`` signature of ``body``."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    return hmac.compare_digest(compute_signature(secret, body), header)


class PullRequestEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    delivery_id: str
    action: str
    installation_id: int
    repo_full_name: str
    pr_number: int
    head_sha: str
    base_sha: str
    head_ref: str
    draft: bool
    author: str
    sender: str

    @property
    def should_review(self) -> bool:
        return self.action in REVIEW_ACTIONS


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def parse_pull_request_event(headers: Mapping[str, str], body: bytes) -> PullRequestEvent | None:
    """Parse a ``pull_request`` delivery. Returns None for other event types.

    Raises ``InvalidWebhook`` if the event is a pull_request but the payload is malformed.
    """
    event = _header(headers, "x-github-event")
    if event != "pull_request":
        return None
    delivery = _header(headers, "x-github-delivery")
    if not delivery:
        raise InvalidWebhook("missing X-GitHub-Delivery header")
    try:
        data: Any = json.loads(body)
        pr = data["pull_request"]
        return PullRequestEvent(
            delivery_id=delivery,
            action=str(data["action"]),
            installation_id=int(data["installation"]["id"]),
            repo_full_name=str(data["repository"]["full_name"]),
            pr_number=int(pr["number"]),
            head_sha=str(pr["head"]["sha"]),
            base_sha=str(pr["base"]["sha"]),
            head_ref=str(pr["head"]["ref"]),
            draft=bool(pr.get("draft", False)),
            author=str((pr.get("user") or {}).get("login", "")),
            sender=str((data.get("sender") or {}).get("login", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidWebhook(f"malformed pull_request payload: {error}") from error


class PushEvent(BaseModel):
    """A push to a branch: open pull requests targeting it may have just become conflicting."""

    model_config = ConfigDict(frozen=True)

    delivery_id: str
    installation_id: int
    repo_full_name: str
    branch: str
    deleted: bool
    sender: str

    @property
    def should_check(self) -> bool:
        return not self.deleted


def parse_push_event(headers: Mapping[str, str], body: bytes) -> PushEvent | None:
    """Parse a ``push`` delivery for a branch. None for other events and for tag pushes."""
    if _header(headers, "x-github-event") != "push":
        return None
    delivery = _header(headers, "x-github-delivery")
    if not delivery:
        raise InvalidWebhook("missing X-GitHub-Delivery header")
    try:
        data: Any = json.loads(body)
        ref = str(data["ref"])
        if not ref.startswith("refs/heads/"):
            return None
        return PushEvent(
            delivery_id=delivery,
            installation_id=int(data["installation"]["id"]),
            repo_full_name=str(data["repository"]["full_name"]),
            branch=ref.removeprefix("refs/heads/"),
            deleted=bool(data.get("deleted", False)),
            sender=str((data.get("sender") or {}).get("login", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidWebhook(f"malformed push payload: {error}") from error
