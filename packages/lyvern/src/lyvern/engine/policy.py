"""Per-repository review policy. Defaults are conservative: approval is off."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lyvern.engine.contracts import Severity


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- which GitHub review events the bot may submit (ED-018)
    allow_request_changes: bool = True
    allow_approve: bool = False  # explicit per-repository opt-in

    # --- what counts as blocking
    blocking_severities: frozenset[Severity] = frozenset({Severity.CRITICAL, Severity.HIGH})
    min_confidence_to_block: float = Field(default=0.8, ge=0.0, le=1.0)

    # --- conditions for APPROVE (all must hold)
    required_stages: frozenset[str] = frozenset({"diff", "static_analysis"})
    max_unanalyzed_share: float = Field(default=0.0, ge=0.0, le=1.0)
    approve_max_risk_score: int = Field(default=30, ge=0, le=100)
    # even a non-blocking finding at/above this severity prevents an approval
    approve_blocked_by_severity: Severity = Severity.MEDIUM

    # --- publishing limits
    max_inline_comments: int = Field(default=25, ge=0, le=100)
    min_severity_for_inline: Severity = Severity.LOW
