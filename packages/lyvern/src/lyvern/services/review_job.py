"""Run one review: read the PR, analyse it, publish the review, record the outcome."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lyvern.config import Settings, get_settings
from lyvern.db import get_engine
from lyvern.db.models import ReviewRun
from lyvern.engine.contracts import ReviewEvent, RunStatus
from lyvern.engine.policy import ReviewPolicy
from lyvern.github.app_auth import AppAuth
from lyvern.github.client import GitHubReadClient
from lyvern.github.publisher import GitHubPublisher, ReviewComment, WriteGuard
from lyvern.github.refs import PullRequestRef
from lyvern.review_pipeline import PullRequestSource, review_pull_request

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _newer_run_exists(session: Session, run: ReviewRun) -> bool:
    newer = session.scalar(
        select(ReviewRun.id)
        .where(
            ReviewRun.repo_full_name == run.repo_full_name,
            ReviewRun.pr_number == run.pr_number,
            ReviewRun.created_at > run.created_at,
        )
        .limit(1)
    )
    return newer is not None


def _dismiss_stale_changes_requested(
    session: Session, publisher: GitHubPublisher, run: ReviewRun, head_sha: str
) -> None:
    stale = session.scalars(
        select(ReviewRun).where(
            ReviewRun.repo_full_name == run.repo_full_name,
            ReviewRun.pr_number == run.pr_number,
            ReviewRun.id != run.id,
            ReviewRun.event_posted == ReviewEvent.REQUEST_CHANGES.value,
            ReviewRun.github_review_id.is_not(None),
            ReviewRun.changes_dismissed.is_(False),
        )
    ).all()
    for old in stale:
        assert old.github_review_id is not None  # filtered above  # noqa: S101
        try:
            dismissed = publisher.dismiss_review(
                run.repo_full_name,
                run.pr_number,
                old.github_review_id,
                f"Dismissed automatically: the blocking findings from the earlier review are no "
                f"longer present in commit {head_sha[:8]}. A person should still review it.",
            )
        except Exception:
            logger.exception("could not dismiss an earlier review")
            continue
        if dismissed:
            old.changes_dismissed = True
            session.commit()


def execute_review(
    engine: Engine,
    run_id: UUID,
    *,
    make_source: Callable[[int], PullRequestSource],
    publisher: GitHubPublisher,
    policy: ReviewPolicy,
) -> None:
    with Session(engine) as session:
        run = session.get(ReviewRun, run_id)
        if run is None or run.status != "queued":
            return  # unknown or already handled: idempotent
        run.status = "running"
        run.started_at = _now()
        session.commit()
        repo, number = run.repo_full_name, run.pr_number
        installation_id = run.installation_id

        try:
            owner, _, name = repo.partition("/")
            draft = review_pull_request(
                make_source(installation_id), PullRequestRef(owner, name, number), policy
            )
            session.refresh(run)
            if _newer_run_exists(session, run) or not draft.decision.publish:
                run.status = "superseded"
                run.finished_at = _now()
                session.commit()
                return

            comments = [
                ReviewComment(path=p, line=ln, body=text, start_line=start)
                for p, ln, start, text in draft.inline
            ]
            result = publisher.publish_review(
                repo, number, draft.pr.head_sha, draft.decision.event, draft.summary, comments
            )
            run.status = "partial" if draft.state.run_status == RunStatus.PARTIAL else "succeeded"
            run.event_posted = result.event_posted.value
            run.github_review_id = result.review_id
            run.findings_count = len(draft.findings)
            run.inline_posted = result.inline_posted
            run.finished_at = _now()
            session.commit()
            logger.info(
                "review published",
                extra={"repo": repo, "pr": number, "event": result.event_posted.value},
            )
            # A "changes requested" review stays active on GitHub until its author dismisses
            # or replaces it. If this complete review found nothing blocking, dismiss ours.
            if result.event_posted != ReviewEvent.REQUEST_CHANGES and not draft.decision.incomplete:
                _dismiss_stale_changes_requested(session, publisher, run, draft.pr.head_sha)
        except Exception as error:
            session.rollback()
            run = session.get(ReviewRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(error).__name__}: {str(error)[:400]}"
                run.finished_at = _now()
                session.commit()
            logger.exception("review failed", extra={"repo": repo, "pr": number})


def execute_review_from_settings(run_id: UUID, settings: Settings | None = None) -> None:
    """Production wiring: App credentials from settings, installation token per run."""
    settings = settings or get_settings()
    if not (settings.github_app_id and settings.github_app_private_key_path):
        raise RuntimeError("GitHub App id and private key path are not configured")
    auth = AppAuth.from_key_file(settings.github_app_id, settings.github_app_private_key_path)
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(ReviewRun, run_id)
        installation_id = run.installation_id if run else 0
    publisher = GitHubPublisher(
        WriteGuard.from_setting(settings.write_allowed_repos),
        lambda: auth.installation_token(installation_id),
    )
    try:
        execute_review(
            engine,
            run_id,
            make_source=lambda inst: GitHubReadClient(auth.installation_token(inst)),
            publisher=publisher,
            policy=ReviewPolicy(),
        )
    finally:
        publisher.close()
        auth.close()
