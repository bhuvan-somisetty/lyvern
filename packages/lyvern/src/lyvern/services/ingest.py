"""Turn a verified webhook delivery into a recorded, de-duplicated review run.

The signature must already have been checked by the caller. Idempotency comes from two
database unique constraints: the delivery id (a redelivered event does nothing) and
(repository, pull request, head commit) (the same commit is never reviewed twice).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lyvern.db.models import ReviewRun, WebhookDelivery
from lyvern.github.publisher import WriteGuard, WriteNotAllowed
from lyvern.github.webhook import InvalidWebhook, parse_pull_request_event, parse_push_event


@dataclass(frozen=True)
class IngestResult:
    http_status: int
    status: str  # queued | ignored | rejected | duplicate | duplicate_run | invalid
    run_id: UUID | None = None
    detail: str = ""


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    return next((v for k, v in headers.items() if k.lower() == lowered), None)


def ingest_delivery(
    engine: Engine,
    headers: Mapping[str, str],
    body: bytes,
    guard: WriteGuard,
    enqueue: Callable[[UUID], object],
    enqueue_conflict_check: Callable[[str, int, str], object] | None = None,
) -> IngestResult:
    event = _header(headers, "x-github-event") or ""
    delivery_id = _header(headers, "x-github-delivery") or ""
    if not delivery_id:
        return IngestResult(400, "invalid", detail="missing X-GitHub-Delivery")

    if event == "push":
        return _ingest_push(engine, headers, body, guard, enqueue_conflict_check)

    try:
        pr = parse_pull_request_event(headers, body)
    except InvalidWebhook as error:
        return IngestResult(400, "invalid", detail=str(error)[:200])

    with Session(engine) as session:
        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            event=event[:64],
            action=pr.action if pr else None,
            installation_id=pr.installation_id if pr else None,
            repo_full_name=pr.repo_full_name if pr else None,
            status="ignored",
        )
        session.add(delivery)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return IngestResult(200, "duplicate", detail="delivery already processed")

        if pr is None:
            delivery.detail = f"event '{event}' is not handled"
            session.commit()
            return IngestResult(202, "ignored", detail=delivery.detail)
        if not pr.should_review:
            delivery.detail = f"action '{pr.action}' does not start a review"
            session.commit()
            return IngestResult(202, "ignored", detail=delivery.detail)
        try:
            guard.assert_allowed(pr.repo_full_name)
        except WriteNotAllowed as error:
            delivery.status = "rejected"
            delivery.detail = str(error)[:300]
            session.commit()
            return IngestResult(202, "rejected", detail="repository is not on the write allowlist")

        run = ReviewRun(
            repo_full_name=pr.repo_full_name,
            pr_number=pr.pr_number,
            head_sha=pr.head_sha,
            installation_id=pr.installation_id,
            trigger_delivery_id=delivery_id,
            status="queued",
        )
        session.add(run)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            with Session(engine) as again:  # keep the delivery row, mark it as a duplicate commit
                again.add(
                    WebhookDelivery(
                        delivery_id=delivery_id,
                        event=event[:64],
                        action=pr.action,
                        installation_id=pr.installation_id,
                        repo_full_name=pr.repo_full_name,
                        status="duplicate_run",
                        detail="this head commit was already reviewed",
                    )
                )
                again.commit()
            return IngestResult(
                200, "duplicate_run", detail="this head commit was already reviewed"
            )

        delivery.status = "queued"
        run_id = run.id
        session.commit()
    enqueue(run_id)
    return IngestResult(202, "queued", run_id=run_id)


def _ingest_push(
    engine: Engine,
    headers: Mapping[str, str],
    body: bytes,
    guard: WriteGuard,
    enqueue_conflict_check: Callable[[str, int, str], object] | None,
) -> IngestResult:
    delivery_id = _header(headers, "x-github-delivery") or ""
    try:
        push = parse_push_event(headers, body)
    except InvalidWebhook as error:
        return IngestResult(400, "invalid", detail=str(error)[:200])

    with Session(engine) as session:
        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            event="push",
            action=None,
            installation_id=push.installation_id if push else None,
            repo_full_name=push.repo_full_name if push else None,
            status="ignored",
        )
        session.add(delivery)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return IngestResult(200, "duplicate", detail="delivery already processed")

        if push is None or not push.should_check:
            delivery.detail = "push is not to an existing branch"
            session.commit()
            return IngestResult(202, "ignored", detail=delivery.detail)
        if enqueue_conflict_check is None:
            delivery.detail = "conflict re-check is not configured"
            session.commit()
            return IngestResult(202, "ignored", detail=delivery.detail)
        try:
            guard.assert_allowed(push.repo_full_name)
        except WriteNotAllowed as error:
            delivery.status = "rejected"
            delivery.detail = str(error)[:300]
            session.commit()
            return IngestResult(202, "rejected", detail="repository is not on the write allowlist")
        delivery.status = "queued"
        delivery.detail = f"conflict re-check for branch {push.branch}"[:300]
        session.commit()
    enqueue_conflict_check(push.repo_full_name, push.installation_id, push.branch)
    return IngestResult(202, "queued", detail="conflict re-check queued")
