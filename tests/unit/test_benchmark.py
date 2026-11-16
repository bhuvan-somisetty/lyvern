"""Benchmark harness: statistics, synthetic suite, and the real-PR comparison with a fake client."""

import json
from pathlib import Path

import pytest

from lyvern import cli
from lyvern.benchmark.metrics import Confusion, count_matched, fmt_ratio, wilson_interval, within
from lyvern.benchmark.real_prs import (
    human_comments,
    precision_from_labels,
    run_real_benchmark,
    write_adjudication_sheet,
)
from lyvern.benchmark.synthetic import CASES, Case, run_synthetic
from lyvern.github.client import GitHubError
from lyvern.github.models import ChangedFileInfo, PullRequestInfo, ReviewCommentInfo
from lyvern.github.refs import PullRequestRef

# ---------------------------------------------------------------------------- statistics


def test_wilson_interval_matches_known_values() -> None:
    lo, hi = wilson_interval(7, 10)
    assert (round(lo, 3), round(hi, 3)) == (0.397, 0.892)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and lo > 0.69
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi < 0.31


def test_small_samples_get_wide_intervals_and_formatting_is_explicit() -> None:
    assert fmt_ratio(0, 0) == "n/a (0 cases)"
    assert fmt_ratio(7, 10) == "7/10 = 70.0% (95% CI 39.7-89.2%)"
    lo1, hi1 = wilson_interval(1, 1)
    lo2, hi2 = wilson_interval(100, 100)
    assert (hi1 - lo1) > (hi2 - lo2)


def test_confusion_precision_recall_f1_and_undefined_cases() -> None:
    c = Confusion(tp=6, fp=2, fn=4)
    assert (c.precision, c.recall) == (0.75, 0.6)
    assert c.f1 == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))
    empty = Confusion()
    assert empty.precision is None and empty.recall is None and empty.f1 is None
    total = Confusion(1, 1, 1)
    total.add(c)
    assert (total.tp, total.fp, total.fn) == (7, 3, 5)


def test_location_matching_uses_file_and_tolerance() -> None:
    assert within(("a", 10), ("a", 13), 3) and not within(("a", 10), ("a", 14), 3)
    assert not within(("a", 10), ("b", 10), 3)
    assert count_matched([("a", 10), ("a", 50), ("b", 1)], [("a", 12), ("b", 9)], 3) == 1


# ------------------------------------------------------------------------ synthetic suite


def test_synthetic_suite_is_balanced_and_currently_has_no_disagreements() -> None:
    report = run_synthetic()
    assert report.cases == len(CASES) >= 60
    assert report.positives >= 25 and report.negatives >= 25
    assert report.disagreements == []
    assert (report.overall.fp, report.overall.fn) == (
        0,
        0,
    ) and report.overall.tp == report.positives


def test_synthetic_report_surfaces_misses_and_unexpected_findings() -> None:
    cases = (
        Case("expects-nothing-but-flagged", "a.js", "eval(x);\n", ()),
        Case("expects-more-than-exists", "a.js", "const a = 1;\n", (("lyvern-js:eval", 1),)),
        Case("correct", "a.js", "eval(x);\n", (("lyvern-js:eval", 1),)),
    )
    report = run_synthetic(cases)
    assert (report.overall.tp, report.overall.fp, report.overall.fn) == (1, 1, 1)
    assert any("UNEXPECTED" in d for d in report.disagreements)
    assert any("MISSED" in d for d in report.disagreements)
    text = report.render()
    assert "Caveat: the author wrote both the rules and these cases" in text


# ------------------------------------------------------------------- real-PR comparison

PY = "import os\n\n\ndef f(items=[]):\n    return eval(items)\n"
PATCH = "@@ -0,0 +1,5 @@\n" + "".join(f"+{line}\n" for line in PY.split("\n")[:-1])


def comment(
    path: str, line: int, author: str = "alice", kind: str = "User", reply: int | None = None
) -> ReviewCommentInfo:
    return ReviewCommentInfo(
        path=path, body="x", author=author, author_type=kind, line=line, in_reply_to_id=reply
    )


class FakeClient:
    def __init__(self, comments: list[ReviewCommentInfo], fail: bool = False) -> None:
        self.comments, self.fail = comments, fail

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        if self.fail:
            raise GitHubError(404, "Not Found")
        return PullRequestInfo(
            owner=ref.owner, repo=ref.repo, number=ref.number, title="Sample", body="", author="a",
            state="closed", draft=False, html_url="u", base_ref="main", base_sha="b" * 40,
            head_ref="x", head_sha="a" * 40, head_repo_full_name=f"{ref.owner}/{ref.repo}",
            changed_files=1, additions=5, deletions=0,
        )  # fmt: skip

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        return [
            ChangedFileInfo(
                filename="app.py", status="added", additions=5, deletions=0, patch=PATCH
            )
        ]

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return PY

    def list_review_comments(self, ref: PullRequestRef) -> list[ReviewCommentInfo]:
        return self.comments


def test_human_comment_filter_drops_bots_replies_and_unanchored_comments() -> None:
    comments = [
        comment("a.py", 5),
        comment("a.py", 6, author="coderabbitai[bot]", kind="Bot"),
        comment("a.py", 7, author="dependabot[bot]", kind="User"),
        comment("a.py", 8, reply=123),
        ReviewCommentInfo(path="a.py", body="x", author="bob", author_type="User"),  # no line
        ReviewCommentInfo(path="", body="x", author="bob", author_type="User", line=3),
        ReviewCommentInfo(path="a.py", body="x", author="bob", author_type="User", original_line=9),
    ]
    kept = human_comments(comments)
    assert [(c.path, c.anchor_line) for c in kept] == [("a.py", 5), ("a.py", 9)]


def test_real_benchmark_counts_coverage_agreement_and_builds_an_adjudication_sheet(
    tmp_path: Path,
) -> None:
    ref = PullRequestRef("o", "r", 1)
    # findings: lines 1 (F401), 4 (B006), 5 (S307); humans commented on 5 and 20; a bot on 4
    client = FakeClient(
        [
            comment("app.py", 5),
            comment("app.py", 20),
            comment("app.py", 4, author="x[bot]", kind="Bot"),
        ]
    )
    report = run_real_benchmark(client, [ref], tolerance=3)  # type: ignore[arg-type]
    (result,) = report.results
    assert result.error == "" and result.findings >= 3 and result.inline >= 3
    assert (
        result.human_comments == 2 and result.human_matched == 1
    )  # only the one on line 5 is near a finding
    assert result.ours_matched >= 1
    text = report.render()
    assert "1 PRs reviewed read-only" in text and "Human coverage" in text and "Agreement" in text
    assert "not precision" in text
    sheet = tmp_path / "sheet.jsonl"
    write_adjudication_sheet(report, str(sheet))
    rows = [json.loads(line) for line in sheet.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == result.findings and all(r["label"] is None for r in rows)
    assert {"pr", "path", "line", "rule", "evidence"} <= set(rows[0])


def test_failed_pr_is_reported_not_hidden() -> None:
    report = run_real_benchmark(FakeClient([], fail=True), [PullRequestRef("o", "r", 9)])  # type: ignore[arg-type]
    assert report.results[0].error and "FAILED" in report.render() and report.ok == []


def test_precision_comes_only_from_human_labels() -> None:
    rows = [
        {"label": "true_positive"}, {"label": "true_positive"}, {"label": "false_positive"},
        {"label": "unsure"}, {"label": None}, {},
    ]  # fmt: skip
    confusion, unlabelled = precision_from_labels(rows)
    assert (confusion.tp, confusion.fp, unlabelled) == (2, 1, 3)
    assert confusion.precision == pytest.approx(2 / 3)


def test_cli_benchmark_synthetic_prints_the_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["benchmark", "synthetic"]) == 0
    out = capsys.readouterr().out
    assert "Synthetic benchmark:" in out and "Disagreements: none" in out


def test_cli_benchmark_real_requires_a_readable_pr_list(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert cli.main(["benchmark", "real", "--prs", str(tmp_path / "missing.txt")]) == 2
    assert "error" in capsys.readouterr().err
