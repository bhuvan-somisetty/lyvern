"""Reviewer-mode pipeline and CLI with a fake read-only source (real diff parser, real ruff)."""

import json
from typing import Any

import pytest

from lyvern import cli
from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.contracts import ReviewEvent, RunStatus
from lyvern.engine.decision import StageState
from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef
from lyvern.review_pipeline import review_pull_request

REF = PullRequestRef("octo", "repo", 7)

A_PY = "import os\n\n\ndef f(items=[]):\n    return eval(items)\n\n\nprint(undefined_name)\n"
A_PATCH = "@@ -0,0 +1,8 @@\n" + "".join(f"+{line}\n" for line in A_PY.split("\n")[:-1])

B_PY = 'import os\nx = eval("1")\ndef g():\n    return 1\nprint(undefined_name)\n'
B_PATCH = '@@ -2,3 +2,4 @@\n x = eval("1")\n def g():\n     return 1\n+print(undefined_name)\n'


def pr_info() -> PullRequestInfo:
    return PullRequestInfo(
        owner="octo", repo="repo", number=7, title="Change", body="", author="alice",
        state="open", draft=False, html_url="https://github.com/octo/repo/pull/7",
        base_ref="main", base_sha="b" * 40, head_ref="x", head_sha="a" * 40,
        head_repo_full_name="alice/repo", changed_files=0, additions=0, deletions=0,
    )  # fmt: skip


def f(
    name: str, status: str = "modified", patch: str | None = None, adds: int = 1
) -> ChangedFileInfo:
    return ChangedFileInfo(filename=name, status=status, additions=adds, deletions=0, patch=patch)


class FakeSource:
    def __init__(self, files: list[ChangedFileInfo], contents: dict[str, str | None]) -> None:
        self.files, self.contents = files, contents
        self.calls: list[str] = []

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        self.calls.append("get_pull_request")
        return pr_info()

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        self.calls.append("list_changed_files")
        return self.files

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        self.calls.append(f"get_file_text:{repo_full_name}@{ref[:4]}")
        return self.contents.get(path)


def standard_source() -> FakeSource:
    files = [
        f("a.py", "added", A_PATCH, 8),
        f("b.py", "modified", B_PATCH, 1),
        f("svc/main.go", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
        f("README.md", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
        f("old.py", "removed", "@@ -1 +0,0 @@\n-x\n"),
        f("logo.bin", "added", None),
    ]
    return FakeSource(files, {"a.py": A_PY, "b.py": B_PY})


def test_draft_review_end_to_end_on_a_sample_pr() -> None:
    src = standard_source()
    draft = review_pull_request(src, REF)

    sources = {fi.detection_source for fi in draft.findings}
    assert {"ruff:S307", "ruff:F821", "ruff:B006", "ruff:F401"} <= sources

    # inline comments are only on lines the PR added
    inline = {(p, ln) for p, ln, _s, _t in draft.inline}
    assert ("a.py", 5) in inline and ("a.py", 8) in inline and ("b.py", 5) in inline
    assert ("b.py", 1) not in inline and ("b.py", 2) not in inline  # pre-existing, unchanged lines
    dropped = {(d.finding.file_path, d.finding.line_start) for d in draft.placement.dropped}
    assert ("b.py", 1) in dropped and ("b.py", 2) in dropped

    # blocking confirmed findings -> proposed REQUEST_CHANGES, and never an approval
    assert draft.decision.event == ReviewEvent.REQUEST_CHANGES
    assert (
        "Result: Changes requested." in draft.summary
        and "does not replace human review" in draft.summary
    )

    # honest accounting of what was not analysed
    reasons = dict(draft.unanalyzed)
    assert reasons["svc/main.go"] == "no analyser for this file type yet"
    assert "no patch" in reasons["logo.bin"]
    assert (
        "README.md" not in reasons and "old.py" not in reasons
    )  # docs and removed files are not counted
    assert draft.state.files_total == 4  # a.py, b.py, main.go, logo.bin
    assert draft.state.files_unanalyzed == 2


def test_pipeline_only_uses_read_methods_and_reads_the_head_repo() -> None:
    src = standard_source()
    review_pull_request(src, REF)
    assert {c.split(":")[0] for c in src.calls} == {
        "get_pull_request",
        "list_changed_files",
        "get_file_text",
    }
    assert "get_file_text:alice/repo@aaaa" in src.calls  # fork head repo, head sha


CLEAN_FILES = [f("ok.py", "added", "@@ -0,0 +1,2 @@\n+def add(a, b):\n+    return a + b\n", 2)]
CLEAN_CONTENT = {"ok.py": "def add(a, b):\n    return a + b\n"}


def test_small_clean_pr_is_approved_only_when_the_repository_opted_in() -> None:
    from lyvern.engine.policy import ReviewPolicy

    off = review_pull_request(FakeSource(CLEAN_FILES, CLEAN_CONTENT), REF)
    assert off.decision.event == ReviewEvent.COMMENT
    assert any("not enabled" in r for r in off.decision.reasons)

    on = review_pull_request(
        FakeSource(CLEAN_FILES, CLEAN_CONTENT), REF, ReviewPolicy(allow_approve=True)
    )
    assert on.findings == () and on.risk.level == "low" and on.risk.score < 30
    assert on.decision.event == ReviewEvent.APPROVE
    assert "Approved by automated policy" in on.summary and "not by a person" in on.summary
    assert f"Risk: {on.risk.score}/100 (low)" in on.summary


def test_unanalysed_files_or_a_failed_analyser_prevent_approval_even_on_a_clean_pr() -> None:
    from lyvern.engine.policy import ReviewPolicy

    files = [*CLEAN_FILES, f("svc/main.go", "added", "@@ -0,0 +1 @@\n+package main\n")]
    draft = review_pull_request(
        FakeSource(files, CLEAN_CONTENT), REF, ReviewPolicy(allow_approve=True)
    )
    assert draft.decision.event == ReviewEvent.COMMENT
    assert any("could not be analyzed" in r for r in draft.decision.reasons)
    assert draft.risk.factors[-1].name == "unanalyzed" and draft.risk.factors[-1].points > 0


def test_risky_change_cannot_be_approved_even_with_no_findings() -> None:
    from lyvern.engine.policy import ReviewPolicy

    patch = "@@ -0,0 +1,3 @@\n+a = 1\n+b = 2\n+c = 3\n"
    files = [f(f"auth/mod{i}.py", "added", patch, 3) for i in range(11)] + [
        f("migrations/0001.sql", "added", patch, 3),
        f(".github/workflows/ci.yml", "added", patch, 3),
    ]
    contents = {x.filename: "a = 1\nb = 2\nc = 3\n" for x in files}
    draft = review_pull_request(FakeSource(files, contents), REF, ReviewPolicy(allow_approve=True))
    assert draft.findings == () and draft.risk.score > 30
    assert draft.decision.event == ReviewEvent.COMMENT
    assert any("exceeds the approval ceiling" in r for r in draft.decision.reasons)


def test_analyzer_failure_marks_the_run_partial_and_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AnalyzerError("ruff timed out after 20s")

    monkeypatch.setattr("lyvern.review_pipeline.analyze_python", boom)
    draft = review_pull_request(standard_source(), REF)
    assert draft.state.run_status == RunStatus.PARTIAL
    assert draft.state.stages["static_analysis"] == StageState.FAILED
    assert draft.decision.incomplete and "analyser failed" in dict(draft.unanalyzed)["a.py"]
    assert "incomplete" in draft.summary


def test_missing_content_and_unparseable_patch_are_listed_not_hidden() -> None:
    files = [
        f("gone.py", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
        f("bad.py", "modified", "garbage\n"),
    ]
    draft = review_pull_request(FakeSource(files, {"gone.py": None}), REF)
    reasons = dict(draft.unanalyzed)
    assert (
        "content unavailable" in reasons["gone.py"] and "could not be parsed" in reasons["bad.py"]
    )


# ------------------------------------------------------------------------------------ cli


def test_cli_text_and_json_output_state_that_nothing_was_posted() -> None:
    draft = review_pull_request(standard_source(), REF)
    text = cli.format_draft(draft)
    assert "DRAFT REVIEW - NOTHING WAS POSTED" in text and "Nothing was posted to GitHub." in text
    assert "Proposed verdict: REQUEST_CHANGES" in text and "a.py:5" in text
    data = cli.draft_to_json(draft)
    assert data["posted"] is False and data["proposed_event"] == "REQUEST_CHANGES"
    json.dumps(data)  # must be serialisable


def test_cli_main_runs_with_a_fake_client_and_handles_bad_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeClient(FakeSource):
        def __init__(self, token: str | None) -> None:
            super().__init__(standard_source().files, {"a.py": A_PY, "b.py": B_PY})

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "GitHubReadClient", FakeClient)
    monkeypatch.setattr(cli, "resolve_token", lambda: "t")
    assert cli.main(["review", "octo/repo#7"]) == 0
    assert "NOTHING WAS POSTED" in capsys.readouterr().out
    assert cli.main(["review", "octo/repo#7", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["posted"] is False
    assert cli.main(["review", "not a ref"]) == 2
    assert "not a pull request reference" in capsys.readouterr().err


def test_cli_has_no_command_that_posts() -> None:
    parser = cli.build_parser()
    commands = next(a for a in parser._actions if getattr(a, "choices", None)).choices  # type: ignore[attr-defined]
    assert set(commands) == {"review"}


def test_typescript_and_javascript_files_are_analysed_with_real_inline_placement() -> None:
    ts_code = "const a = 1;\nexport function run(input: string) {\n  return eval(input);\n}\n"
    ts_patch = "@@ -0,0 +1,4 @@\n" + "".join(f"+{line}\n" for line in ts_code.split("\n")[:-1])
    files = [
        f("web/run.ts", "added", ts_patch, 4),
        f("web/ok.js", "added", "@@ -0,0 +1 @@\n+const x = 1;\n"),
    ]
    draft = review_pull_request(
        FakeSource(files, {"web/run.ts": ts_code, "web/ok.js": "const x = 1;\n"}), REF
    )
    assert {x.detection_source for x in draft.findings} == {"lyvern-js:eval"}
    assert {(p, ln) for p, ln, _s, _t in draft.inline} == {("web/run.ts", 3)}
    assert draft.unanalyzed == () and draft.state.files_total == 2
    assert (
        draft.decision.event == ReviewEvent.REQUEST_CHANGES
    )  # eval confidence 0.80 meets the threshold


def test_pre_existing_js_issue_outside_the_change_is_not_reported() -> None:
    code = "eval(old);\nconst keep = 1;\nconst added = 2;\n"
    patch = "@@ -1,2 +1,3 @@\n eval(old);\n const keep = 1;\n+const added = 2;\n"
    draft = review_pull_request(FakeSource([f("a.js", "modified", patch)], {"a.js": code}), REF)
    assert draft.inline == () and {d.finding.line_start for d in draft.placement.dropped} == {1}
