"""Reviewer-mode pipeline: read a pull request, analyse it, return a DRAFT review.

Nothing here can write to GitHub: the source protocol only has read methods.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers.deps import (
    DependencyLookup,
    DependencyLookupError,
    analyze_manifest,
    is_manifest,
)
from lyvern.engine.analyzers.go import analyze_go
from lyvern.engine.analyzers.go import is_supported as is_go
from lyvern.engine.analyzers.js_ts import analyze_js_ts
from lyvern.engine.analyzers.js_ts import is_supported as is_js_ts
from lyvern.engine.analyzers.ruff import analyze_python
from lyvern.engine.analyzers.xref import check_removed_symbols
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
from lyvern.github.models import ChangedFileInfo, MergeState, PullRequestInfo
from lyvern.github.refs import PullRequestRef
from lyvern.llm.base import LlmError
from lyvern.ml.features import extract_features
from lyvern.ml.model import AttentionEstimate, AttentionModel, render_attention

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
    merge_state: MergeState | None = None
    attention: AttentionEstimate | None = None


def _merge_state(source: object, ref: PullRequestRef) -> MergeState | None:
    """Best effort: a source that cannot say (or fails) leaves mergeability unknown."""
    getter = getattr(source, "get_merge_state", None)
    if not callable(getter):
        return None
    try:
        state = getter(ref)
    except Exception:
        return None
    return state if isinstance(state, MergeState) else None


Analyzer = Callable[[str, str, set[int]], list[Finding]]


def _run_python(path: str, text: str, added: set[int]) -> list[Finding]:
    return analyze_python(path, text, added_lines=added)


def _js_ts_runner(include_noisy: bool) -> Analyzer:
    def run(path: str, text: str, added: set[int]) -> list[Finding]:
        return analyze_js_ts(path, text, added_lines=added, include_noisy=include_noisy)

    return run


def _run_go(path: str, text: str, added: set[int]) -> list[Finding]:
    return analyze_go(path, text, added_lines=added)


def _manifest_analyzer(lookup: DependencyLookup) -> Analyzer:
    def run(path: str, text: str, added: set[int]) -> list[Finding]:
        return analyze_manifest(path, text, lookup, added_lines=added)

    return run


def _analyzer_for(path: str, strict_style: bool = False) -> Analyzer | None:
    if path.endswith(".py"):
        return _run_python
    if is_js_ts(path):
        return _js_ts_runner(strict_style)
    if is_go(path):
        return _run_go
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
    deps: DependencyLookup | None = None,
    attention: AttentionModel | None = None,
    cross_file: bool = False,
    strict_style: bool = False,
) -> DraftReview:
    policy = policy or ReviewPolicy()
    pr = source.get_pull_request(ref)
    changed = source.list_changed_files(ref)
    merge_state = _merge_state(source, ref)

    diffs: dict[str, FileDiff] = {}
    raw_findings: list[Finding] = []
    unanalyzed: list[tuple[str, str]] = []
    analyzer_failed = False
    deps_failed = False
    xref_failed = False
    considered = 0  # files that exist after the PR and are source code

    for info in changed:
        manifest = deps is not None and is_manifest(info.filename)
        if info.status == "removed" or (_is_non_code(info.filename) and not manifest):
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

        analyzer = _analyzer_for(info.filename, strict_style)
        if analyzer is None and manifest and deps is not None:
            analyzer = _manifest_analyzer(deps)

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
        except DependencyLookupError as error:
            deps_failed = True
            unanalyzed.append((info.filename, f"dependency check failed: {error}"))
        except AnalyzerError as error:
            analyzer_failed = True
            unanalyzed.append((info.filename, f"analyser failed: {error}"))

    xref_on = cross_file and callable(getattr(source, "list_repo_files", None))
    if xref_on:
        try:
            raw_findings += check_removed_symbols(
                source,  # type: ignore[arg-type]  # checked above: it has list_repo_files
                pr.head_repo_full_name,
                pr.head_sha,
                diffs,
            )
        except AnalyzerError:
            xref_failed = True

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
            if analyzer_failed or deps_failed or xref_failed or llm_stage == StageState.FAILED
            else RunStatus.SUCCEEDED
        ),
        stages={
            "diff": StageState.COMPLETED,
            "static_analysis": StageState.FAILED if analyzer_failed else StageState.COMPLETED,
            "risk": StageState.COMPLETED,
            **({"llm": llm_stage} if llm_stage is not None else {}),
            **(
                {"cross_file": StageState.FAILED if xref_failed else StageState.COMPLETED}
                if xref_on
                else {}
            ),
            **(
                {"dependencies": StageState.FAILED if deps_failed else StageState.COMPLETED}
                if deps is not None
                else {}
            ),
        },
        files_total=considered,
        files_unanalyzed=len(unanalyzed),
        risk_score=risk.score,
        merge_conflicts=merge_state is not None and merge_state.has_conflicts,
    )
    decision = decide(findings, state, policy)
    estimate = (
        attention.estimate(extract_features(pr, changed))
        if attention is not None and attention.displayable
        else None
    )
    summary = render_summary(
        product_name=PRODUCT_NAME,
        decision=decision,
        state=state,
        findings=findings,
        placement=placement,
        unanalyzed=unanalyzed,
        risk=risk,
        ai_note=_ai_note(llm_result, llm_error),
        attention_note=render_attention(estimate) if estimate is not None else None,
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
        merge_state=merge_state,
        attention=estimate,
        summary=summary,
        inline=inline,
    )
