"""Read-only dashboard API. Real data from the database only; locked behind a bearer token.

Secure by default: if ``LYVERN_API_TOKEN`` is not configured every endpoint answers 503, and a
wrong or missing token answers 401. There are no write endpoints here.
"""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lyvern.config import get_settings
from lyvern.db import ReviewRun, WebhookDelivery, get_engine

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    configured = get_settings().api_token
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=503, detail="dashboard API token is not configured")
    expected = configured.get_secret_value()
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid or missing token")


class RunOut(BaseModel):
    id: UUID
    repo: str
    pr_number: int
    pr_url: str
    head_sha: str
    status: str
    event_posted: str | None
    findings_count: int | None
    inline_posted: int | None
    changes_dismissed: bool
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StatsOut(BaseModel):
    runs_total: int
    runs_by_status: dict[str, int]
    runs_by_event: dict[str, int]
    findings_total: int
    inline_comments_total: int
    deliveries_total: int
    deliveries_by_status: dict[str, int]
    last_run_at: datetime | None


def _run_out(run: ReviewRun) -> RunOut:
    return RunOut(
        id=run.id,
        repo=run.repo_full_name,
        pr_number=run.pr_number,
        pr_url=f"https://github.com/{run.repo_full_name}/pull/{run.pr_number}",
        head_sha=run.head_sha,
        status=run.status,
        event_posted=run.event_posted,
        findings_count=run.findings_count,
        inline_posted=run.inline_posted,
        changes_dismissed=bool(run.changes_dismissed),
        error=(run.error or None) and run.error[:300],
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/runs", response_model=list[RunOut], dependencies=[Depends(require_token)])
def list_runs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    repo: Annotated[str | None, Query(max_length=200)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
) -> list[RunOut]:
    query = select(ReviewRun).order_by(ReviewRun.created_at.desc()).limit(limit)
    if repo:
        query = query.where(ReviewRun.repo_full_name == repo)
    if status:
        query = query.where(ReviewRun.status == status)
    with Session(get_engine()) as session:
        return [_run_out(r) for r in session.scalars(query)]


@router.get("/runs/{run_id}", response_model=RunOut, dependencies=[Depends(require_token)])
def get_run(run_id: UUID) -> RunOut:
    with Session(get_engine()) as session:
        run = session.get(ReviewRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _run_out(run)


@router.get("/stats", response_model=StatsOut, dependencies=[Depends(require_token)])
def stats() -> StatsOut:
    with Session(get_engine()) as s:
        by_status = dict(
            s.execute(select(ReviewRun.status, func.count()).group_by(ReviewRun.status)).all()
        )
        by_event = {
            (event or "none"): count
            for event, count in s.execute(
                select(ReviewRun.event_posted, func.count()).group_by(ReviewRun.event_posted)
            ).all()
        }
        deliveries = dict(
            s.execute(
                select(WebhookDelivery.status, func.count()).group_by(WebhookDelivery.status)
            ).all()
        )
        return StatsOut(
            runs_total=sum(by_status.values()),
            runs_by_status=by_status,
            runs_by_event=by_event,
            findings_total=int(
                s.scalar(select(func.coalesce(func.sum(ReviewRun.findings_count), 0))) or 0
            ),
            inline_comments_total=int(
                s.scalar(select(func.coalesce(func.sum(ReviewRun.inline_posted), 0))) or 0
            ),
            deliveries_total=sum(deliveries.values()),
            deliveries_by_status=deliveries,
            last_run_at=s.scalar(select(func.max(ReviewRun.created_at))),
        )
