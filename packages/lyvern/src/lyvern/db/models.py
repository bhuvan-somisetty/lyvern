"""Tables for webhook deliveries and review runs (the database is the source of truth)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
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
    changes_dismissed: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FindingRecord(Base):
    """One finding the bot reported in one run. Kept so people can label it right or wrong."""

    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("review_runs.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(80))
    file_path: Mapped[str] = mapped_column(String(500))
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(24))
    origin: Mapped[str] = mapped_column(String(24))
    detection_source: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Float)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    placed_inline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FindingFeedback(Base):
    """A person's verdict on a finding (one per finding; changing it overwrites it)."""

    __tablename__ = "finding_feedback"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("findings.id", ondelete="CASCADE"), unique=True
    )
    verdict: Mapped[str] = mapped_column(String(16))  # true_positive | false_positive | unsure
    reviewer: Mapped[str | None] = mapped_column(String(32))  # who gave the verdict
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    """A dashboard account. Only a scrypt hash of the password is stored."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))  # viewer | reviewer | admin
    disabled: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
