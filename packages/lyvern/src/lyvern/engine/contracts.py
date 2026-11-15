"""Core data contracts shared by the engine, worker and API.

Invariants live in the types so that no code path can publish a finding that
breaks them (evidence required, valid line range, LLM output never blocking
without corroboration).
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Category(StrEnum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    RELIABILITY = "reliability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class Origin(StrEnum):
    """Where a finding came from. Never merged or relabelled downstream."""

    STATIC_ANALYSIS = "static_analysis"
    ML_PREDICTION = "ml_prediction"
    LLM_OBSERVATION = "llm_observation"
    HUMAN_CONFIRMED = "human_confirmed"


class ReviewEvent(StrEnum):
    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    APPROVE = "APPROVE"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class Finding(BaseModel):
    """One reviewable issue. Frozen: dedup/ranking create new objects, never mutate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin
    detection_source: str = Field(min_length=1, description="tool/rule/model id and version")
    file_path: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    evidence: str = Field(description="code excerpt or rule trace that supports the finding")
    impact: str = ""
    recommended_fix: str = ""
    introduced_by_pr: bool = True
    blocking: bool = False
    corroborated_by: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        if not self.evidence.strip():
            raise ValueError("a finding without evidence is not allowed")
        if self.blocking and self.origin == Origin.LLM_OBSERVATION and not self.corroborated_by:
            raise ValueError("an uncorroborated LLM observation can never be blocking")
        if self.blocking and self.origin == Origin.ML_PREDICTION and not self.corroborated_by:
            raise ValueError("an uncorroborated ML prediction can never be blocking")
        return self

    @property
    def fingerprint(self) -> str:
        """Stable identity for dedup and recurrence: ignores line numbers and wording.

        Built from category, file, detection source and the whitespace-normalized
        evidence, so the same issue keeps its fingerprint when surrounding code moves.
        """
        normalized = re.sub(r"\s+", " ", self.evidence).strip().lower()
        raw = "\x1f".join([self.category.value, self.file_path, self.detection_source, normalized])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
