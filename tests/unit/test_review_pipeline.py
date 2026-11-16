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
        f("web/app.tsx", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
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
    assert reasons["web/app.tsx"] == "no analyser for this file type yet"
    assert "no patch" in reasons["logo.bin"]
    assert (
        "README.md" not in reasons and "old.py" not in reasons
    )  # docs and removed files are not counted
    assert draft.state.files_total == 4  # a.py, b.py, app.tsx, logo.bin
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


def test_clean_pr_with_unanalysed_files_can_never_be_approved() -> None:
    files = [f("ok.py", "added", "@@ -0,0 +1,2 @@\n+def add(a, b):\n+    return a + b\n", 2)]
    from lyvern.engine.policy import ReviewPolicy

    draft = review_pull_request(
        FakeSource(files, {"ok.py": "def add(a, b):\n    return a + b\n"}),
        REF,
        ReviewPolicy(allow_approve=True),
    )
    assert draft.findings == ()
    assert (
        draft.decision.event == ReviewEvent.COMMENT
    )  # risk stage does not exist yet -> no approval
    assert any("risk was not assessed" in r for r in draft.decision.reasons)


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
