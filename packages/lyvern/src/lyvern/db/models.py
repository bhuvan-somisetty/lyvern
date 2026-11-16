"""Tables for webhook deliveries and review runs (the database is the source of truth)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from lyvern.db.base import Base


class WebhookDelivery(Base):
    """One row per GitHub delivery id. The unique id is what makes event handling idempotent."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    delivery_id: Mapped[str] = mapped_column(String(80), unique=True)
    event: Mapped[str] = mapped_column(String(64))
    action: Mapped[str | None] = mapped_column(String(64))
    installation_id: Mapped[int | None] = mapped_column(BigInteger)
    repo_full_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24))  # queued | ignored | rejected | duplicate_run
    detail: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewRun(Base):
    """One automated review of one pull request head commit."""

    __tablename__ = "review_runs"
    __table_args__ = (
        UniqueConstraint("repo_full_name", "pr_number", "head_sha", name="uq_review_runs_pr_head"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    repo_full_name: Mapped[str] = mapped_column(String(200))
    pr_number: Mapped[int] = mapped_column(Integer)
    head_sha: Mapped[str] = mapped_column(String(64))
    installation_id: Mapped[int] = mapped_column(BigInteger)
    trigger_delivery_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    event_posted: Mapped[str | None] = mapped_column(String(24))
    github_review_id: Mapped[int | None] = mapped_column(BigInteger)
    findings_count: Mapped[int | None] = mapped_column(Integer)
    inline_posted: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
