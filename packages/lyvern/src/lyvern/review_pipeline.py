"""Reviewer-mode pipeline: read a pull request, analyse it, return a DRAFT review.

Nothing here can write to GitHub: the source protocol only has read methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from lyvern.engine.analyzers import AnalyzerError
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
from lyvern.engine.placement import Placement, plan_placement
from lyvern.engine.policy import ReviewPolicy
from lyvern.engine.render import render_inline, render_summary
from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef

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
    unanalyzed: tuple[tuple[str, str], ...]
    summary: str
    inline: tuple[tuple[str, int, int | None, str], ...]  # path, line, start_line, text


def _is_non_code(path: str) -> bool:
    p = PurePosixPath(path)
    return p.name in _NON_CODE_NAMES or p.suffix.lower() in _NON_CODE_SUFFIXES


def review_pull_request(
    source: PullRequestSource,
    ref: PullRequestRef,
    policy: ReviewPolicy | None = None,
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

        if not info.filename.endswith(".py"):
            unanalyzed.append((info.filename, "no analyser for this file type yet"))
            continue
        text = source.get_file_text(pr.head_repo_full_name, info.filename, pr.head_sha)
        if text is None:
            unanalyzed.append(
                (info.filename, "file content unavailable (missing, binary or large)")
            )
            continue
        try:
            raw_findings += analyze_python(info.filename, text, added_lines=set(fd.added_lines()))
        except AnalyzerError as error:
            analyzer_failed = True
            unanalyzed.append((info.filename, f"analyser failed: {error}"))

    findings = rank(mark_blocking(dedupe(raw_findings), policy))
    placement = plan_placement(findings, diffs, policy)
    state = AnalysisState(
        run_status=RunStatus.PARTIAL if analyzer_failed else RunStatus.SUCCEEDED,
        stages={
            "diff": StageState.COMPLETED,
            "static_analysis": StageState.FAILED if analyzer_failed else StageState.COMPLETED,
        },
        files_total=considered,
        files_unanalyzed=len(unanalyzed),
        risk_score=None,  # the risk stage is not built yet, so approval is never possible
    )
    decision = decide(findings, state, policy)
    summary = render_summary(
        product_name=PRODUCT_NAME,
        decision=decision,
        state=state,
        findings=findings,
        placement=placement,
        unanalyzed=unanalyzed,
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
        unanalyzed=tuple(unanalyzed),
        summary=summary,
        inline=inline,
    )
