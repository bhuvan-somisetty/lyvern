"""Re-check open pull requests after a push to their target branch.

A push to ``main`` can make an open pull request conflict without any change to the pull
request itself, so GitHub sends no ``pull_request`` event. For each open pull request that
now has conflicts this posts the conflict notice (once per head commit) and withdraws the
bot's own earlier approval, because that approval no longer describes a mergeable change.
"""

from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lyvern.config import Settings, get_settings
from lyvern.db import get_engine
from lyvern.engine.conflict import render_conflict_notice
from lyvern.engine.contracts import ReviewEvent
from lyvern.github.app_auth import AppAuth
from lyvern.github.client import GitHubReadClient
from lyvern.github.models import MergeState, PullRequestInfo
from lyvern.github.publisher import GitHubPublisher, WriteGuard
from lyvern.github.refs import PullRequestRef
from lyvern.services.review_job import dismiss_own_reviews

logger = logging.getLogger(__name__)

MAX_PULL_REQUESTS = 50


class ConflictSource(Protocol):
    def list_open_pull_requests(
        self, owner: str, repo: str, base: str, *, limit: int = ...
    ) -> list[PullRequestInfo]: ...

    def get_merge_state(self, ref: PullRequestRef) -> MergeState: ...


def check_open_pull_requests(
    engine: Engine,
    source: ConflictSource,
    publisher: GitHubPublisher,
    repo: str,
    branch: str,
) -> int:
    """Returns how many pull requests were found conflicting. Never raises for one bad PR."""
    owner, _, name = repo.partition("/")
    conflicting = 0
    for pr in source.list_open_pull_requests(owner, name, branch, limit=MAX_PULL_REQUESTS):
        if pr.draft:
            continue
        ref = PullRequestRef(owner, name, pr.number)
        try:
            state = source.get_merge_state(ref)
            if not state.has_conflicts:
                continue
            conflicting += 1
            body = render_conflict_notice(pr.base_ref, pr.head_ref, pr.head_sha)
            publisher.post_conflict_notice(repo, pr.number, body, pr.head_sha)
            with Session(engine) as session:
                dismiss_own_reviews(
                    session,
                    publisher,
                    repo,
                    pr.number,
                    ReviewEvent.APPROVE,
                    f"Dismissed automatically: {branch} changed and this pull request now has "
                    "merge conflicts, so an earlier approval no longer applies.",
                )
        except Exception:
            logger.exception("conflict check failed for one pull request", extra={"pr": pr.number})
    return conflicting


def check_from_settings(
    repo: str, installation_id: int, branch: str, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    if not (settings.github_app_id and settings.github_app_private_key_path):
        raise RuntimeError("GitHub App id and private key path are not configured")
    auth = AppAuth.from_key_file(settings.github_app_id, settings.github_app_private_key_path)
    publisher = GitHubPublisher(
        WriteGuard.from_setting(settings.write_allowed_repos),
        lambda: auth.installation_token(installation_id),
    )
    source = GitHubReadClient(auth.installation_token(installation_id))
    try:
        return check_open_pull_requests(get_engine(), source, publisher, repo, branch)
    finally:
        source.close()
        publisher.close()
        auth.close()
