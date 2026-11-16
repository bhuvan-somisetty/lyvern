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
from lyvern.db.models import FindingRecord, ReviewRun
from lyvern.engine.analyzers.deps import DependencyLookup, OsvClient
from lyvern.engine.conflict import render_conflict_notice
from lyvern.engine.contracts import ReviewEvent, RunStatus
from lyvern.engine.llm_review import LlmReviewer
from lyvern.engine.policy import ReviewPolicy
from lyvern.github.app_auth import AppAuth
from lyvern.github.client import GitHubReadClient
from lyvern.github.models import MergeState, PullRequestInfo
from lyvern.github.publisher import GitHubPublisher, ReviewComment, WriteGuard
from lyvern.github.refs import PullRequestRef
from lyvern.llm.factory import make_llm_reviewer
from lyvern.review_pipeline import DraftReview, PullRequestSource, review_pull_request

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


def dismiss_own_reviews(
    session: Session,
    publisher: GitHubPublisher,
    repo: str,
    pr_number: int,
    event: ReviewEvent,
    message: str,
    *,
    exclude_run: UUID | None = None,
) -> None:
    """Dismiss OUR earlier reviews of this kind on the PR (the column marks any dismissal)."""
    query = select(ReviewRun).where(
        ReviewRun.repo_full_name == repo,
        ReviewRun.pr_number == pr_number,
        ReviewRun.event_posted == event.value,
        ReviewRun.github_review_id.is_not(None),
        ReviewRun.changes_dismissed.is_(False),
    )
    if exclude_run is not None:
        query = query.where(ReviewRun.id != exclude_run)
    stale = session.scalars(query).all()
    for old in stale:
        assert old.github_review_id is not None  # filtered above  # noqa: S101
        try:
            dismissed = publisher.dismiss_review(repo, pr_number, old.github_review_id, message)
        except Exception:
            logger.exception("could not dismiss an earlier review")
            continue
        if dismissed:
            old.changes_dismissed = True
            session.commit()


def _dismiss_stale_changes_requested(
    session: Session, publisher: GitHubPublisher, run: ReviewRun, head_sha: str
) -> None:
    dismiss_own_reviews(
        session,
        publisher,
        run.repo_full_name,
        run.pr_number,
        ReviewEvent.REQUEST_CHANGES,
        f"Dismissed automatically: the blocking findings from the earlier review are no "
        f"longer present in commit {head_sha[:8]}. A person should still review it.",
        exclude_run=run.id,
    )


def _dismiss_stale_approvals(
    session: Session, publisher: GitHubPublisher, run: ReviewRun, head_sha: str
) -> None:
    """An approval only speaks for the commit it saw: withdraw it once a later review declines."""
    dismiss_own_reviews(
        session,
        publisher,
        run.repo_full_name,
        run.pr_number,
        ReviewEvent.APPROVE,
        f"Dismissed automatically: the latest review of commit {head_sha[:8]} did not approve "
        "it (see that review for the reason). An earlier approval no longer applies.",
        exclude_run=run.id,
    )


def _notify_merge_conflicts(
    publisher: GitHubPublisher, pr: PullRequestInfo, ref: PullRequestRef, state: MergeState | None
) -> None:
    """Tell the author about merge conflicts. Best effort: never fails or changes the run."""
    if state is None or not state.has_conflicts:
        return
    try:
        body = render_conflict_notice(pr.base_ref, pr.head_ref, pr.head_sha)
        if publisher.post_conflict_notice(f"{ref.owner}/{ref.repo}", ref.number, body, pr.head_sha):
            logger.info("merge conflict notice posted", extra={"pr": ref.number})
    except Exception:
        logger.exception("could not post the merge conflict notice")


MAX_STORED_FINDINGS = 200


def _save_findings(session: Session, run_id: UUID, draft: DraftReview) -> None:
    """Keep what was reported so a person can mark each finding right or wrong later."""
    placed = {
        (c.finding.file_path, c.finding.line_start, c.finding.detection_source)
        for c in draft.placement.inline
    }
    for f in draft.findings[:MAX_STORED_FINDINGS]:
        session.add(
            FindingRecord(
                run_id=run_id,
                fingerprint=f.fingerprint,
                file_path=f.file_path[:500],
                line_start=f.line_start,
                line_end=f.line_end,
                severity=f.severity.value,
                category=f.category.value,
                origin=f.origin.value,
                detection_source=f.detection_source[:120],
                title=f.title[:200],
                confidence=f.confidence,
                blocking=f.blocking,
                placed_inline=(f.file_path, f.line_start, f.detection_source) in placed,
            )
        )


def execute_review(
    engine: Engine,
    run_id: UUID,
    *,
    make_source: Callable[[int], PullRequestSource],
    publisher: GitHubPublisher,
    policy: ReviewPolicy,
    llm: LlmReviewer | None = None,
    deps: DependencyLookup | None = None,
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
                make_source(installation_id),
                PullRequestRef(owner, name, number),
                policy,
                llm=llm,
                deps=deps,
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
            _save_findings(session, run.id, draft)
            session.commit()
            logger.info(
                "review published",
                extra={"repo": repo, "pr": number, "event": result.event_posted.value},
            )
            # A "changes requested" review stays active on GitHub until its author dismisses
            # or replaces it. If this complete review found nothing blocking, dismiss ours.
            if result.event_posted != ReviewEvent.REQUEST_CHANGES and not draft.decision.incomplete:
                _dismiss_stale_changes_requested(session, publisher, run, draft.pr.head_sha)
            if result.event_posted != ReviewEvent.APPROVE:
                _dismiss_stale_approvals(session, publisher, run, draft.pr.head_sha)
            _notify_merge_conflicts(
                publisher, draft.pr, PullRequestRef(owner, name, number), draft.merge_state
            )
        except Exception as error:
            session.rollback()
            run = session.get(ReviewRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(error).__name__}: {str(error)[:400]}"
                run.finished_at = _now()
                session.commit()
            logger.exception("review failed", extra={"repo": repo, "pr": number})


def policy_for_repo(repo_full_name: str, settings: Settings) -> ReviewPolicy:
    """Approval is an explicit per-repository opt-in (exact, case-insensitive owner/name)."""
    allowed = {r.strip().lower() for r in settings.approve_allowed_repos.split(",") if r.strip()}
    return ReviewPolicy(allow_approve=repo_full_name.lower() in allowed)


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
        repo_full_name = run.repo_full_name if run else ""
    publisher = GitHubPublisher(
        WriteGuard.from_setting(settings.write_allowed_repos),
        lambda: auth.installation_token(installation_id),
    )
    osv = OsvClient() if settings.dependency_check.strip().lower() == "osv" else None
    try:
        execute_review(
            engine,
            run_id,
            make_source=lambda inst: GitHubReadClient(auth.installation_token(inst)),
            publisher=publisher,
            policy=policy_for_repo(repo_full_name, settings),
            llm=make_llm_reviewer(settings.llm_provider, settings),
            deps=osv,
        )
    finally:
        if osv is not None:
            osv.close()
        publisher.close()
        auth.close()
