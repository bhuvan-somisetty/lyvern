"""Review decision engine (ED-018): findings + run state + policy -> one GitHub review event.

Pure and deterministic. Every downgrade records a human-readable reason that ends up
in the review body, so a reader can see why a review was COMMENT instead of APPROVE.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from lyvern.engine.contracts import Finding, Origin, ReviewEvent, RunStatus
from lyvern.engine.policy import ReviewPolicy

# origins whose output is deterministic or human-verified
_TRUSTED_ORIGINS = frozenset({Origin.STATIC_ANALYSIS, Origin.HUMAN_CONFIRMED})


class StageState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Merge conflicts are reported in their own comment, never inside the review text.
MERGE_CONFLICT_REASON = "the pull request has merge conflicts"


@dataclass(frozen=True)
class AnalysisState:
    """What actually ran. Built by the orchestrator from real step outcomes."""

    run_status: RunStatus
    stages: Mapping[str, StageState] = field(default_factory=dict)
    files_total: int = 0
    files_unanalyzed: int = 0  # unsupported language, binary, too large, parse failure
    risk_score: int | None = None  # 0-100, None if the risk stage did not complete
    merge_conflicts: bool = False  # GitHub reports the PR cannot be merged (known conflicts only)

    @property
    def unanalyzed_share(self) -> float:
        return 0.0 if self.files_total == 0 else self.files_unanalyzed / self.files_total


@dataclass(frozen=True)
class Decision:
    event: ReviewEvent
    publish: bool  # False for superseded/cancelled runs: nothing is posted
    incomplete: bool  # True if the review must say that some analysis did not complete
    blocking: tuple[Finding, ...]
    reasons: tuple[str, ...]
    wanted: ReviewEvent  # what the findings alone called for, before policy gates


def is_blocking(finding: Finding, policy: ReviewPolicy) -> bool:
    """Can this finding block a merge? Evidence quality matters more than severity.

    Requires: severity in the policy's blocking set, introduced by this PR, confidence
    at or above the threshold, and a trustworthy basis (deterministic/human origin, or
    corroboration by an independent detection source). An uncorroborated LLM
    observation or ML prediction is never blocking.
    """
    if finding.severity not in policy.blocking_severities:
        return False
    if not finding.introduced_by_pr:
        return False
    if finding.confidence < policy.min_confidence_to_block:
        return False
    return finding.origin in _TRUSTED_ORIGINS or bool(finding.corroborated_by)


def mark_blocking(findings: Iterable[Finding], policy: ReviewPolicy) -> list[Finding]:
    """Return findings with ``blocking`` set according to ``is_blocking`` (validated copies)."""
    out: list[Finding] = []
    for f in findings:
        should = is_blocking(f, policy)
        out.append(
            f
            if f.blocking == should
            else Finding.model_validate({**f.model_dump(), "blocking": should})
        )
    return out


def decide(findings: Iterable[Finding], state: AnalysisState, policy: ReviewPolicy) -> Decision:
    items = list(findings)
    blocking = tuple(f for f in items if is_blocking(f, policy))
    reasons: list[str] = []

    if state.run_status in (RunStatus.SUPERSEDED, RunStatus.CANCELLED):
        return Decision(
            event=ReviewEvent.COMMENT,
            publish=False,
            incomplete=True,
            blocking=blocking,
            reasons=(f"run {state.run_status.value}: nothing is published",),
            wanted=ReviewEvent.COMMENT,
        )
    if state.run_status in (RunStatus.QUEUED, RunStatus.RUNNING):
        raise ValueError("cannot decide on a run that has not finished")

    failed = sorted(s for s, v in state.stages.items() if v != StageState.COMPLETED)
    incomplete = state.run_status != RunStatus.SUCCEEDED or bool(failed)
    if incomplete:
        detail = ", ".join(failed) if failed else state.run_status.value
        reasons.append(f"analysis was incomplete ({detail})")

    wanted = ReviewEvent.REQUEST_CHANGES if blocking else ReviewEvent.APPROVE
    if state.run_status == RunStatus.FAILED:
        # a failed run produced no trustworthy result: neutral status only
        return Decision(
            event=ReviewEvent.COMMENT,
            publish=True,
            incomplete=True,
            blocking=(),
            reasons=tuple(reasons),
            wanted=ReviewEvent.COMMENT,
        )

    if blocking:
        if policy.allow_request_changes:
            return Decision(
                ReviewEvent.REQUEST_CHANGES, True, incomplete, blocking, tuple(reasons), wanted
            )
        reasons.append("blocking findings exist but this repository does not allow request-changes")
        return Decision(ReviewEvent.COMMENT, True, incomplete, blocking, tuple(reasons), wanted)

    approve_reasons = _approve_obstacles(items, state, policy)
    if not approve_reasons:
        return Decision(ReviewEvent.APPROVE, True, False, (), tuple(reasons), wanted)
    reasons.extend(approve_reasons)
    return Decision(ReviewEvent.COMMENT, True, incomplete, (), tuple(reasons), wanted)


def _approve_obstacles(
    findings: list[Finding], state: AnalysisState, policy: ReviewPolicy
) -> list[str]:
    obstacles: list[str] = []
    if not policy.allow_approve:
        obstacles.append("approval is not enabled for this repository")
    if state.merge_conflicts:
        obstacles.append(MERGE_CONFLICT_REASON)
    if state.run_status != RunStatus.SUCCEEDED:
        obstacles.append(f"run status is {state.run_status.value}, not succeeded")
    missing = sorted(
        s for s in policy.required_stages if state.stages.get(s) != StageState.COMPLETED
    )
    if missing:
        obstacles.append("required stage(s) did not complete: " + ", ".join(missing))
    other_failed = sorted(
        s
        for s, v in state.stages.items()
        if v != StageState.COMPLETED and s not in policy.required_stages
    )
    if other_failed:
        obstacles.append("stage(s) did not complete: " + ", ".join(other_failed))
    if state.unanalyzed_share > policy.max_unanalyzed_share:
        obstacles.append(
            f"{state.files_unanalyzed} of {state.files_total} changed files could not be analyzed"
        )
    if state.risk_score is None:
        obstacles.append("risk was not assessed")
    elif state.risk_score > policy.approve_max_risk_score:
        obstacles.append(
            f"risk score {state.risk_score} exceeds the approval ceiling "
            f"{policy.approve_max_risk_score}"
        )
    serious = [
        f
        for f in findings
        if f.introduced_by_pr and f.severity.rank >= policy.approve_blocked_by_severity.rank
    ]
    if serious:
        obstacles.append(
            f"{len(serious)} finding(s) left to address (approval requires none, even minor ones)"
        )
    return obstacles
