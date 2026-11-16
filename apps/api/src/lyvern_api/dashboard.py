"""Read-only dashboard API. Real data from the database only; locked behind a bearer token.

Secure by default: if ``LYVERN_API_TOKEN`` is not configured every endpoint answers 503, and a
wrong or missing token answers 401. The only write is a person's verdict on a finding.
"""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lyvern.auth import can_label
from lyvern.benchmark.metrics import wilson_interval
from lyvern.config import get_settings
from lyvern.db import FindingFeedback, FindingRecord, ReviewRun, WebhookDelivery, get_engine
from lyvern.services.users import authenticate

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


Verdict = Literal["true_positive", "false_positive", "unsure"]


class FindingOut(BaseModel):
    id: UUID
    run_id: UUID
    file_path: str
    line_start: int
    line_end: int
    severity: str
    category: str
    origin: str
    detection_source: str
    title: str
    confidence: float
    blocking: bool
    placed_inline: bool
    verdict: str | None
    note: str | None


class FeedbackIn(BaseModel):
    verdict: Verdict
    note: str | None = None
    reviewer: str | None = None  # username, set by the web server after it checked the role


class SourcePrecision(BaseModel):
    source: str
    true_positive: int
    false_positive: int
    unsure: int
    precision: float | None


class FeedbackSummary(BaseModel):
    findings_total: int
    labelled: int  # findings with any verdict
    true_positive: int
    false_positive: int
    unsure: int
    precision: float | None  # true / (true + false); 'unsure' is excluded, never guessed
    precision_ci_low: float | None
    precision_ci_high: float | None
    by_source: list[SourcePrecision]


def _finding_out(record: FindingRecord, feedback: FindingFeedback | None) -> FindingOut:
    return FindingOut(
        id=record.id,
        run_id=record.run_id,
        file_path=record.file_path,
        line_start=record.line_start,
        line_end=record.line_end,
        severity=record.severity,
        category=record.category,
        origin=record.origin,
        detection_source=record.detection_source,
        title=record.title,
        confidence=record.confidence,
        blocking=record.blocking,
        placed_inline=record.placed_inline,
        verdict=feedback.verdict if feedback else None,
        note=feedback.note if feedback else None,
    )


@router.get(
    "/runs/{run_id}/findings",
    response_model=list[FindingOut],
    dependencies=[Depends(require_token)],
)
def run_findings(run_id: UUID) -> list[FindingOut]:
    with Session(get_engine()) as s:
        if s.get(ReviewRun, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        rows = s.execute(
            select(FindingRecord, FindingFeedback)
            .outerjoin(FindingFeedback, FindingFeedback.finding_id == FindingRecord.id)
            .where(FindingRecord.run_id == run_id)
            .order_by(FindingRecord.file_path, FindingRecord.line_start)
        ).all()
        return [_finding_out(rec, fb) for rec, fb in rows]


@router.put(
    "/findings/{finding_id}/feedback",
    response_model=FindingOut,
    dependencies=[Depends(require_token)],
)
def set_feedback(finding_id: UUID, body: FeedbackIn) -> FindingOut:
    note = (body.note or "").strip()[:500] or None
    with Session(get_engine()) as s:
        record = s.get(FindingRecord, finding_id)
        if record is None:
            raise HTTPException(status_code=404, detail="finding not found")
        feedback = s.scalar(select(FindingFeedback).where(FindingFeedback.finding_id == finding_id))
        if feedback is None:
            feedback = FindingFeedback(
                finding_id=finding_id, verdict=body.verdict, note=note, reviewer=body.reviewer
            )
            s.add(feedback)
        else:
            feedback.verdict, feedback.note, feedback.reviewer = body.verdict, note, body.reviewer
        s.commit()
        s.refresh(feedback)
        return _finding_out(record, feedback)


@router.get(
    "/feedback/summary", response_model=FeedbackSummary, dependencies=[Depends(require_token)]
)
def feedback_summary() -> FeedbackSummary:
    with Session(get_engine()) as s:
        total = int(s.scalar(select(func.count()).select_from(FindingRecord)) or 0)
        rows = s.execute(
            select(FindingRecord.detection_source, FindingFeedback.verdict, func.count())
            .join(FindingFeedback, FindingFeedback.finding_id == FindingRecord.id)
            .group_by(FindingRecord.detection_source, FindingFeedback.verdict)
        ).all()
    per_source: dict[str, dict[str, int]] = {}
    for source, verdict, count in rows:
        per_source.setdefault(source, {"true_positive": 0, "false_positive": 0, "unsure": 0})
        per_source[source][verdict] = count
    tp = sum(v["true_positive"] for v in per_source.values())
    fp = sum(v["false_positive"] for v in per_source.values())
    unsure = sum(v["unsure"] for v in per_source.values())
    low = high = None
    if tp + fp:
        low, high = wilson_interval(tp, tp + fp)
    by_source = [
        SourcePrecision(
            source=source,
            true_positive=v["true_positive"],
            false_positive=v["false_positive"],
            unsure=v["unsure"],
            precision=(
                v["true_positive"] / (v["true_positive"] + v["false_positive"])
                if v["true_positive"] + v["false_positive"]
                else None
            ),
        )
        for source, v in sorted(per_source.items())
    ]
    return FeedbackSummary(
        findings_total=total,
        labelled=tp + fp + unsure,
        true_positive=tp,
        false_positive=fp,
        unsure=unsure,
        precision=tp / (tp + fp) if tp + fp else None,
        precision_ci_low=low,
        precision_ci_high=high,
        by_source=by_source,
    )


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    username: str
    role: str
    can_label: bool


_ATTEMPTS: dict[str, list[float]] = {}
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW_SECONDS = 300.0


def _too_many_attempts(key: str, now: float) -> bool:
    recent = [t for t in _ATTEMPTS.get(key, []) if now - t < ATTEMPT_WINDOW_SECONDS]
    _ATTEMPTS[key] = recent
    return len(recent) >= MAX_ATTEMPTS


@router.post("/auth/verify", response_model=LoginOut, dependencies=[Depends(require_token)])
def verify_login(body: LoginIn) -> LoginOut:
    """Check a dashboard login. The web server calls this; it never reveals which part was wrong."""
    import time

    key = body.username.strip().lower()[:64]
    now = time.monotonic()
    if _too_many_attempts(key, now):
        raise HTTPException(status_code=429, detail="too many attempts; wait a few minutes")
    with Session(get_engine()) as session:
        user = authenticate(session, body.username[:64], body.password[:300])
        if user is None:
            _ATTEMPTS.setdefault(key, []).append(now)
            raise HTTPException(status_code=401, detail="invalid username or password")
        _ATTEMPTS.pop(key, None)
        return LoginOut(username=user.username, role=user.role, can_label=can_label(user.role))
