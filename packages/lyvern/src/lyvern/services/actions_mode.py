"""GitHub Actions mode: review a pull request on a free GitHub-hosted runner, no server needed.

The runner is stateless, so the database starts empty. Before reviewing, this module rebuilds the
one thing the review logic needs from history: the bot's own earlier reviews on the pull request
(so a stale "changes requested" or approval can be dismissed). Everything else is unchanged.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lyvern.config import Settings, get_settings
from lyvern.db import get_engine
from lyvern.db.models import ReviewRun
from lyvern.github.app_auth import AppAuth
from lyvern.github.client import GitHubReadClient
from lyvern.github.refs import PullRequestRef
from lyvern.services.review_job import execute_review_from_settings

logger = logging.getLogger(__name__)

_EVENT_FOR_STATE = {
    "APPROVED": "APPROVE",
    "CHANGES_REQUESTED": "REQUEST_CHANGES",
    "COMMENTED": "COMMENT",
}
_HANDLED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def parse_event(payload: dict[str, Any]) -> tuple[str, int, str] | None:
    """(repo, number, head sha) of a pull request event worth reviewing, else None."""
    if payload.get("action") not in _HANDLED_ACTIONS:
        return None
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name")
    number, sha = pr.get("number"), (pr.get("head") or {}).get("sha")
    if not (repo and number and sha) or pr.get("draft"):
        return None
    return str(repo), int(number), str(sha)


def seed_prior_reviews(
    engine: Engine,
    repo: str,
    number: int,
    installation_id: int,
    records: list[dict[str, Any]],
    bot_login: str,
) -> int:
    """Record the bot's own still-active reviews so the normal dismissal logic can find them."""
    seeded = 0
    with Session(engine) as session:
        for record in records:
            event = _EVENT_FOR_STATE.get(str(record.get("state")))
            login = str((record.get("user") or {}).get("login") or "")
            if event is None or login.lower() != bot_login.lower() or not record.get("id"):
                continue  # not ours, dismissed already, or a kind we never dismiss
            submitted = record.get("submitted_at")
            created = (
                datetime.fromisoformat(str(submitted).replace("Z", "+00:00")) if submitted else None
            )
            session.add(
                ReviewRun(
                    repo_full_name=repo,
                    pr_number=number,
                    head_sha=f"{record.get('commit_id', '')}:{record['id']}"[:64],
                    installation_id=installation_id,
                    trigger_delivery_id=f"history-{record['id']}",
                    status="succeeded",
                    event_posted=event,
                    github_review_id=int(record["id"]),
                    created_at=created,
                )
            )
            seeded += 1
        session.commit()
    return seeded


def run_event_file(path: str, settings: Settings | None = None) -> int:
    """Review the pull request in a GitHub event file. Returns a process exit code."""
    settings = settings or get_settings()
    parsed = parse_event(json.loads(Path(path).read_text(encoding="utf-8")))
    if parsed is None:
        print("Nothing to review for this event.")
        return 0
    repo, number, head_sha = parsed
    if not (settings.github_app_id and settings.github_app_private_key_path):
        print("error: the GitHub App id and private key are not configured")
        return 2
    auth = AppAuth.from_key_file(settings.github_app_id, settings.github_app_private_key_path)
    engine = get_engine()
    try:
        installation_id = settings.github_installation_id or auth.installation_for_repo(repo)
        owner, _, name = repo.partition("/")
        reader = GitHubReadClient(auth.installation_token(installation_id))
        try:
            records = reader.list_review_records(PullRequestRef(owner, name, number))
        finally:
            reader.close()
        seeded = seed_prior_reviews(
            engine, repo, number, installation_id, records, auth.bot_login()
        )
        with Session(engine) as session:
            run = ReviewRun(
                repo_full_name=repo,
                pr_number=number,
                head_sha=head_sha,
                installation_id=installation_id,
                trigger_delivery_id=f"actions-{repo}-{number}-{head_sha}",
                status="queued",
            )
            session.add(run)
            session.commit()
            run_id: UUID = run.id
        logger.info("reviewing", extra={"repo": repo, "pr": number, "earlier_reviews": seeded})
        execute_review_from_settings(run_id, settings)
        with Session(engine) as session:
            final = session.get(ReviewRun, run_id)
            status = final.status if final else "unknown"
            posted = final.event_posted if final else None
        print(f"Review of {repo}#{number}: {status}" + (f" ({posted})" if posted else ""))
        return 0 if status in {"succeeded", "partial", "superseded"} else 1
    finally:
        auth.close()
