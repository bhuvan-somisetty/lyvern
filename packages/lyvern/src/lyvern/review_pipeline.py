"""Reviewer-mode pipeline: read a pull request, analyse it, return a DRAFT review.

Nothing here can write to GitHub: the source protocol only has read methods.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers.js_ts import analyze_js_ts
from lyvern.engine.analyzers.js_ts import is_supported as is_js_ts
from lyvern.engine.analyzers.ruff import analyze_python
from lyvern.engine.contracts import Finding, RunStatus
from lyvern.engine.decision import (
    AnalysisState,
    Decision,
    StageState,
    decide,
    mark_blocking,
)
from lyvern.engine.dedup import dedupe, rank
from lyvern.engine.diff import DiffParseError, FileDiff, FileStatus, parse_patch
from lyvern.engine.llm_review import LlmReviewer, LlmReviewResult
from lyvern.engine.placement import Placement, plan_placement
from lyvern.engine.policy import ReviewPolicy
from lyvern.engine.render import render_inline, render_summary
from lyvern.engine.risk import RiskAssessment, RiskFile, assess_risk
from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef
from lyvern.llm.base import LlmError

PRODUCT_NAME = "Lyvern"

# files that are not source code: nothing to analyse, not counted as "not analysed"
_NON_CODE_SUFFIXES = {
    ".md", ".txt", ".rst", ".json", ".yml", ".yaml", ".toml", ".lock", ".svg", ".png",
    ".jpg", ".jpeg", ".gif", ".ico", ".csv", ".snap", ".map", ".ini", ".cfg",
}  # fmt: skip
_NON_CODE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "go.sum"}
_STATUS = {
    "added": FileStatus.ADDED,
    "removed": FileStatus.DELETED,
    "renamed": FileStatus.RENAMED,
}


class PullRequestSource(Protocol):
    """Read-only view of a pull request. Deliberately has no write methods."""

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo: ...
    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]: ...
    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None: ...


@dataclass(frozen=True)
class DraftReview:
    pr: PullRequestInfo
    decision: Decision
    state: AnalysisState
    findings: tuple[Finding, ...]
    placement: Placement
    risk: RiskAssessment
    unanalyzed: tuple[tuple[str, str], ...]
    summary: str
    inline: tuple[tuple[str, int, int | None, str], ...]  # path, line, start_line, text
    llm: LlmReviewResult | None = None
    llm_error: str | None = None


Analyzer = Callable[[str, str, set[int]], list[Finding]]


def _run_python(path: str, text: str, added: set[int]) -> list[Finding]:
    return analyze_python(path, text, added_lines=added)


def _run_js_ts(path: str, text: str, added: set[int]) -> list[Finding]:
    return analyze_js_ts(path, text, added_lines=added)


def _analyzer_for(path: str) -> Analyzer | None:
    if path.endswith(".py"):
        return _run_python
    if is_js_ts(path):
        return _run_js_ts
    return None


def _ai_note(result: LlmReviewResult | None, error: str | None) -> str | None:
    if error is not None:
        return f"AI review could not run ({error}); only deterministic checks were applied."
    if result is None:
        return None
    return (
        f"AI review ({result.model}): {len(result.findings)} observation(s) kept, "
        f"{len(result.dropped)} discarded because they could not be verified against the diff. "
        "AI observations are not independently verified and never block a merge."
    )


def _is_non_code(path: str) -> bool:
    p = PurePosixPath(path)
    return p.name in _NON_CODE_NAMES or p.suffix.lower() in _NON_CODE_SUFFIXES


def review_pull_request(
    source: PullRequestSource,
    ref: PullRequestRef,
    policy: ReviewPolicy | None = None,
    *,
    llm: LlmReviewer | None = None,
) -> DraftReview:
    policy = policy or ReviewPolicy()
    pr = source.get_pull_request(ref)
    changed = source.list_changed_files(ref)

    diffs: dict[str, FileDiff] = {}
    raw_findings: list[Finding] = []
    unanalyzed: list[tuple[str, str]] = []
    analyzer_failed = False
    considered = 0  # files that exist after the PR and are source code

    for info in changed:
        if info.status == "removed" or _is_non_code(info.filename):
            continue
        considered += 1
        if info.patch is None:
            unanalyzed.append((info.filename, "GitHub provided no patch (binary or too large)"))
            continue
        try:
            fd = parse_patch(
                info.patch,
                path=info.filename,
                old_path=info.previous_filename,
                status=_STATUS.get(info.status, FileStatus.MODIFIED),
            )
        except DiffParseError as error:
            unanalyzed.append((info.filename, f"diff could not be parsed: {error}"))
            continue
        diffs[info.filename] = fd

        analyzer = _analyzer_for(info.filename)
        if analyzer is None:
            unanalyzed.append((info.filename, "no analyser for this file type yet"))
            continue
        text = source.get_file_text(pr.head_repo_full_name, info.filename, pr.head_sha)
        if text is None:
            unanalyzed.append(
                (info.filename, "file content unavailable (missing, binary or large)")
            )
            continue
        try:
            raw_findings += analyzer(info.filename, text, set(fd.added_lines()))
        except AnalyzerError as error:
            analyzer_failed = True
            unanalyzed.append((info.filename, f"analyser failed: {error}"))

    llm_result: LlmReviewResult | None = None
    llm_error: str | None = None
    llm_stage: StageState | None = None
    if llm is not None:
        try:
            llm_result = llm.review(pr, diffs)
            raw_findings += list(llm_result.findings)
            llm_stage = StageState.COMPLETED
        except LlmError as error:
            llm_stage = StageState.FAILED
            llm_error = str(error)[:160]

    findings = rank(mark_blocking(dedupe(raw_findings), policy))
    placement = plan_placement(findings, diffs, policy)
    risk = assess_risk(
        files=[
            RiskFile(i.filename, i.additions, i.deletions, is_source=not _is_non_code(i.filename))
            for i in changed
        ],
        findings=findings,
        files_total=considered,
        files_unanalyzed=len(unanalyzed),
    )
    state = AnalysisState(
        run_status=(
            RunStatus.PARTIAL
            if analyzer_failed or llm_stage == StageState.FAILED
            else RunStatus.SUCCEEDED
        ),
        stages={
            "diff": StageState.COMPLETED,
            "static_analysis": StageState.FAILED if analyzer_failed else StageState.COMPLETED,
            "risk": StageState.COMPLETED,
            **({"llm": llm_stage} if llm_stage is not None else {}),
        },
        files_total=considered,
        files_unanalyzed=len(unanalyzed),
        risk_score=risk.score,
    )
    decision = decide(findings, state, policy)
    summary = render_summary(
        product_name=PRODUCT_NAME,
        decision=decision,
        state=state,
        findings=findings,
        placement=placement,
        unanalyzed=unanalyzed,
        risk=risk,
        ai_note=_ai_note(llm_result, llm_error),
    )
    inline = tuple(
        (c.path, c.line, c.start_line, render_inline(c.finding)) for c in placement.inline
    )
    return DraftReview(
        pr=pr,
        decision=decision,
        state=state,
        findings=tuple(findings),
        placement=placement,
        risk=risk,
        unanalyzed=tuple(unanalyzed),
        llm=llm_result,
        llm_error=llm_error,
        summary=summary,
        inline=inline,
    )
