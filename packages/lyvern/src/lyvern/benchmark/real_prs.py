"""Compare Lyvern's draft reviews with what human reviewers actually wrote (read-only).

What this measures, and what it does NOT:

* ``human_recall``: of the inline comments people wrote on a PR, how many sit within
  ``tolerance`` lines of a finding Lyvern raised on the same file. Human comments are mostly
  design, naming and questions that a static analyser cannot raise, so this is expected
  to be low. It is a coverage number, not an accuracy number.
* ``agreement``: of Lyvern's inline findings, how many sit near a human comment. A finding
  with no nearby human comment is NOT necessarily wrong. True precision needs a person to
  label each finding: this module writes an adjudication sheet (JSON lines, label = null)
  and ``precision_from_labels`` computes precision from the labelled file.
* Only reads from GitHub. Bot-authored comments and replies are excluded from the human set.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from lyvern.benchmark.metrics import (
    Confusion,
    Location,
    count_matched,
    fmt_ratio,
)
from lyvern.engine.llm_review import LlmReviewer
from lyvern.github.client import GitHubError, GitHubReadClient
from lyvern.github.models import ReviewCommentInfo
from lyvern.github.refs import PullRequestRef
from lyvern.review_pipeline import review_pull_request


@dataclass
class PrResult:
    ref: str
    title: str
    source_files: int
    unanalyzed: int
    findings: int  # reported on the PR's own changes (inline + general)
    inline: int
    risk_level: str
    event: str
    human_comments: int
    human_matched: int
    ours_matched: int
    error: str = ""
    not_introduced: int = 0  # found in code the PR did not change; never published


@dataclass
class RealReport:
    tolerance: int
    results: list[PrResult] = field(default_factory=list)
    adjudication: list[dict[str, object]] = field(default_factory=list)
    by_rule: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> list[PrResult]:
        return [r for r in self.results if not r.error]

    def render(self) -> str:
        ok = self.ok
        human = sum(r.human_comments for r in ok)
        human_hit = sum(r.human_matched for r in ok)
        inline = sum(r.inline for r in ok)
        ours_hit = sum(r.ours_matched for r in ok)
        with_findings = sum(1 for r in ok if r.findings)
        analysed_files = sum(r.source_files for r in ok)
        lines = [
            f"Real-PR comparison: {len(ok)} PRs reviewed read-only "
            f"({len(self.results) - len(ok)} failed), match tolerance +/-{self.tolerance} lines",
            f"Source files: {analysed_files} considered, {sum(r.unanalyzed for r in ok)} not analysed",
            f"PRs where Lyvern raised at least one finding: {fmt_ratio(with_findings, len(ok))}",
            f"Findings reported on the PRs' own changes: {sum(r.findings for r in ok)} "
            f"({inline} inline); found only in untouched code and NOT reported: "
            f"{sum(r.not_introduced for r in ok)}",
            f"Human coverage (human inline comments near a Lyvern finding): {fmt_ratio(human_hit, human)}",
            f"Agreement (Lyvern inline findings near a human comment): {fmt_ratio(ours_hit, inline)}",
            "By detection source: "
            + (", ".join(f"{k}={v}" for k, v in sorted(self.by_rule.items())) or "none"),
            "Interpretation: coverage is low by design because most human comments are about design "
            "and style; agreement is not precision. Label the adjudication sheet for precision.",
            "",
            "Per PR:",
        ]
        for r in self.results:
            if r.error:
                lines.append(f"- {r.ref}: FAILED ({r.error})")
                continue
            lines.append(
                f"- {r.ref}: {r.source_files} src files, {r.findings} findings ({r.inline} inline, "
                f"{r.not_introduced} pre-existing not reported), "
                f"risk {r.risk_level}, verdict {r.event}; human comments {r.human_comments} "
                f"(near a finding: {r.human_matched}); {r.title[:60]}"
            )
        return "\n".join(lines)


def human_comments(comments: Iterable[ReviewCommentInfo]) -> list[ReviewCommentInfo]:
    """Inline comments written by people on a specific line (no bots, no replies)."""
    return [
        c
        for c in comments
        if c.author_type != "Bot"
        and not c.author.endswith("[bot]")
        and c.in_reply_to_id is None
        and c.path
        and c.anchor_line is not None
    ]


def run_real_benchmark(
    client: GitHubReadClient,
    refs: Sequence[PullRequestRef],
    tolerance: int = 3,
    llm: LlmReviewer | None = None,
) -> RealReport:
    report = RealReport(tolerance=tolerance)
    for ref in refs:
        try:
            draft = review_pull_request(client, ref, llm=llm)
            people = human_comments(client.list_review_comments(ref))
        except GitHubError as error:
            report.results.append(
                PrResult(str(ref), "", 0, 0, 0, 0, "", "", 0, 0, 0, error=str(error)[:80])
            )
            continue
        theirs: list[Location] = [(c.path, c.anchor_line or 0) for c in people]
        ours: list[Location] = [(p, ln) for p, ln, _s, _t in draft.inline]
        reported = [c.finding for c in draft.placement.inline] + [
            g.finding for g in draft.placement.general
        ]
        finding_locs: list[Location] = [(f.file_path, f.line_start) for f in reported]
        report.results.append(
            PrResult(
                ref=str(ref),
                title=draft.pr.title,
                source_files=draft.state.files_total,
                unanalyzed=draft.state.files_unanalyzed,
                findings=len(reported),
                not_introduced=len(draft.placement.dropped),
                inline=len(ours),
                risk_level=draft.risk.level,
                event=draft.decision.event.value,
                human_comments=len(theirs),
                human_matched=count_matched(theirs, finding_locs, tolerance),
                ours_matched=count_matched(ours, theirs, tolerance),
            )
        )
        for f in reported:
            report.by_rule[f.detection_source] += 1
            report.adjudication.append(
                {
                    "pr": str(ref),
                    "path": f.file_path,
                    "line": f.line_start,
                    "rule": f.detection_source,
                    "severity": f.severity.value,
                    "title": f.title,
                    "evidence": f.evidence.split("\n")[0][:160],
                    "introduced_by_pr": f.introduced_by_pr,
                    "label": None,  # set to "true_positive", "false_positive" or "unsure"
                }
            )
    return report


def write_adjudication_sheet(report: RealReport, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in report.adjudication:
            handle.write(json.dumps(row) + "\n")


def precision_from_labels(rows: Iterable[dict[str, object]]) -> tuple[Confusion, int]:
    """Precision from a hand-labelled sheet. Returns (confusion with tp/fp only, unlabelled count)."""
    confusion = Confusion()
    unlabelled = 0
    for row in rows:
        label = row.get("label")
        if label == "true_positive":
            confusion.tp += 1
        elif label == "false_positive":
            confusion.fp += 1
        else:
            unlabelled += 1  # unsure or not yet labelled
    return confusion, unlabelled
