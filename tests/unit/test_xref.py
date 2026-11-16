"""Cross-file check: removed top-level symbols that other files still import or call."""

import pytest

from lyvern.engine.analyzers.xref import (
    MAX_FILES,
    MAX_SYMBOLS,
    CrossFileError,
    check_removed_symbols,
    removed_symbols,
)
from lyvern.engine.contracts import Category, Origin, ReviewEvent, RunStatus, Severity
from lyvern.engine.decision import StageState
from lyvern.engine.diff import FileDiff, parse_patch
from lyvern.engine.policy import ReviewPolicy
from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef
from lyvern.review_pipeline import review_pull_request


def patch(*ops: tuple[str, str]) -> str:
    old = sum(1 for kind, _ in ops if kind in "- ")
    new = sum(1 for kind, _ in ops if kind in "+ ")
    return f"@@ -1,{old} +1,{new} @@\n" + "".join(f"{kind}{text}\n" for kind, text in ops)


def diffs_of(**files: tuple[tuple[str, str], ...]) -> dict[str, FileDiff]:
    return {
        path.replace("__", "/").replace("_dot_", "."): parse_patch(
            patch(*ops), path=path.replace("__", "/").replace("_dot_", ".")
        )
        for path, ops in files.items()
    }


def one(path: str, *ops: tuple[str, str]) -> dict[str, FileDiff]:
    return {path: parse_patch(patch(*ops), path=path)}


# ------------------------------------------------------------------ what counts as removed


def test_a_deleted_top_level_python_function_or_class_is_a_removed_symbol() -> None:
    d = one(
        "pkg/util.py",
        (" ", "import os"),
        ("-", "def legacy_helper(x):"),
        ("-", "    return x"),
        ("-", "class OldWidget:"),
        ("-", "    pass"),
        (" ", "def keep():"),
    )
    found = removed_symbols(d)
    assert [(s.name, s.path, s.group) for s in found] == [
        ("OldWidget", "pkg/util.py", "py"),
        ("legacy_helper", "pkg/util.py", "py"),
    ]
    assert found[0].definition == "class OldWidget:" and found[0].anchor == 2  # next kept line


def test_methods_private_short_common_and_dunder_names_are_not_considered() -> None:
    d = one(
        "a.py",
        ("-", "    def method_inside_class(self):"),
        ("-", "def _private_thing():"),
        ("-", "def tiny():"),
        ("-", "def handler(event):"),
        ("-", "def __getattr__(name):"),
        (" ", "x = 1"),
    )
    assert removed_symbols(d) == []


def test_a_name_that_is_defined_again_anywhere_in_the_change_is_a_move_not_a_removal() -> None:
    d = diffs_of(
        old_dot_py=(("-", "def shared_function():"), (" ", "x = 1")),
        new_dot_py=((" ", "y = 2"), ("+", "def shared_function():")),
    )
    assert removed_symbols(d) == []


def test_javascript_exports_and_go_exported_functions_without_a_receiver() -> None:
    js = one(
        "src/api.ts",
        ("-", "export function fetchEverything() {"),
        ("-", "export const DEFAULT_TIMEOUT = 5;"),
        ("-", "function notExportedLocal() {"),
        (" ", "const a = 1;"),
    )
    assert [s.name for s in removed_symbols(js)] == ["DEFAULT_TIMEOUT", "fetchEverything"]
    go = one(
        "store/db.go",
        ("-", "func OpenDatabase(path string) error {"),
        ("-", "func (s *Store) Method() {"),
        ("-", "func privateOne() {"),
        ("-", "type ConnectionPool struct {"),
        (" ", "package store"),
    )
    assert [s.name for s in removed_symbols(go)] == ["ConnectionPool", "OpenDatabase"]


def test_only_a_bounded_number_of_symbols_is_checked() -> None:
    ops = (*(("-", f"def generated_name_{i}():") for i in range(20)), (" ", "x = 1"))
    assert len(removed_symbols(one("a.py", *ops))) == MAX_SYMBOLS


# ------------------------------------------------------------------- finding references


class Repo:
    def __init__(self, files: dict[str, str], fail: str | None = None) -> None:
        self.files, self.fail = files, fail
        self.read: list[str] = []
        self.listed = 0

    def list_repo_files(self, repo_full_name: str, ref: str) -> list[str]:
        self.listed += 1
        if self.fail == "list":
            raise RuntimeError("secret detail https://x")
        return list(self.files)

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        self.read.append(path)
        if self.fail == "read":
            raise RuntimeError("secret detail")
        return self.files.get(path)


REMOVED = one("pkg/util.py", ("-", "def legacy_helper(x):"), ("-", "    return x"), (" ", "y = 1"))


def check(files: dict[str, str], diffs: dict[str, FileDiff] | None = None) -> list:  # type: ignore[type-arg]
    return check_removed_symbols(Repo(files), "o/r", "a" * 40, diffs or REMOVED)


def test_an_import_or_a_call_in_another_file_is_reported_with_the_reference() -> None:
    (finding,) = check(
        {
            "pkg/util.py": "y = 1\n",
            "pkg/app.py": "from pkg.util import legacy_helper\n\nlegacy_helper(1)\n",
            "other/job.py": "print('x')\n",
        }
    )
    assert finding.detection_source == "lyvern-xref:removed-symbol-still-referenced"
    assert finding.origin == Origin.STATIC_ANALYSIS and finding.category == Category.BUG
    assert finding.severity == Severity.MEDIUM and finding.confidence == 0.7
    assert finding.file_path == "pkg/util.py" and finding.introduced_by_pr is True
    assert "removed: def legacy_helper(x):" in finding.evidence
    assert "pkg/app.py:1: from pkg.util import legacy_helper" in finding.evidence
    assert "`legacy_helper`" in finding.title and "still referenced" in finding.evidence


def test_a_plain_call_is_found_but_method_calls_comments_and_strings_of_other_things_are_not() -> (
    None
):
    assert check({"a.py": "legacy_helper(2)\n"})
    assert check({"a.py": "obj.legacy_helper(2)\n"}) == []  # a method of something else
    assert check({"a.py": "# legacy_helper(2) was removed\n"}) == []
    assert check({"a.py": "legacy_helper_v2(2)\nmy_legacy_helper(1)\n"}) == []  # different names
    assert check({"a.py": "x = 'legacy_helper'\n"}) == []  # not an import or a call


def test_the_defining_file_other_languages_and_vendored_directories_are_skipped() -> None:
    files = {
        "pkg/util.py": "legacy_helper(1)\n",  # the file the symbol was removed from
        "web/app.ts": "legacy_helper(1)\n",  # another language
        "node_modules/x/a.py": "legacy_helper(1)\n",
        "vendor/y/b.py": "legacy_helper(1)\n",
    }
    repo = Repo(files)
    assert check_removed_symbols(repo, "o/r", "a" * 40, REMOVED) == []
    assert repo.read == []  # nothing relevant was even fetched


def test_references_in_files_next_to_the_definition_are_read_first_and_the_budget_is_bounded() -> (
    None
):
    files = {f"zzz/f{i}.py": "x = 1\n" for i in range(MAX_FILES + 30)}
    files["pkg/near.py"] = "legacy_helper(1)\n"
    repo = Repo(files)
    findings = check_removed_symbols(repo, "o/r", "a" * 40, REMOVED)
    assert len(findings) == 1 and repo.read[0] == "pkg/near.py" and len(repo.read) <= MAX_FILES


def test_go_references_are_package_qualified_or_plain_calls() -> None:
    go = one("store/db.go", ("-", "func OpenDatabase(path string) error {"), (" ", "package store"))
    assert check({"cmd/main.go": "err := store.OpenDatabase(p)\n"}, go)
    assert check({"store/other.go": "OpenDatabase(p)\n"}, go)
    assert check({"cmd/main.go": "err := other.OpenDatabase(p)\n"}, go) == []  # a different package


def test_nothing_removed_means_no_repository_reads_at_all() -> None:
    repo = Repo({"a.py": "x"})
    added_only = one("a.py", ("+", "def brand_new_function():"), (" ", "x = 1"))
    assert check_removed_symbols(repo, "o/r", "a" * 40, added_only) == [] and repo.listed == 0


def test_failures_become_a_clean_error_without_leaking_details() -> None:
    for fail in ("list", "read"):
        with pytest.raises(CrossFileError) as info:
            check_removed_symbols(
                Repo({"pkg/app.py": "legacy_helper(1)\n"}, fail=fail), "o/r", "a" * 40, REMOVED
            )
        assert "secret" not in str(info.value) and "http" not in str(info.value)
        assert "RuntimeError" in str(info.value)


# ----------------------------------------------------------------------------- pipeline

REF = PullRequestRef("o", "r", 7)


def pr_info() -> PullRequestInfo:
    return PullRequestInfo(
        owner="o", repo="r", number=7, title="t", body="", author="a", state="open",
        draft=False, html_url="u", base_ref="main", base_sha="b" * 40, head_ref="x",
        head_sha="a" * 40, head_repo_full_name="o/r", changed_files=1, additions=0,
        deletions=2,
    )  # fmt: skip


class Source(Repo):
    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        return pr_info()

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        p = patch(("-", "def legacy_helper(x):"), ("-", "    return x"), (" ", "y = 1"))
        return [
            ChangedFileInfo(
                filename="pkg/util.py", status="modified", additions=0, deletions=2, patch=p
            )
        ]


FILES = {"pkg/util.py": "y = 1\n", "pkg/app.py": "from pkg.util import legacy_helper\n"}


def test_the_pipeline_reports_it_as_a_general_note_and_never_approves() -> None:
    policy = ReviewPolicy(allow_approve=True)
    draft = review_pull_request(Source(FILES), REF, policy, cross_file=True)
    assert [f.detection_source for f in draft.findings] == [
        "lyvern-xref:removed-symbol-still-referenced"
    ]
    assert draft.inline == () and len(draft.placement.general) == 1  # not on an added line
    assert "legacy_helper" in draft.summary
    assert draft.state.stages["cross_file"] == StageState.COMPLETED
    assert draft.decision.event == ReviewEvent.COMMENT  # a finding left to address


def test_a_failed_cross_file_check_makes_the_review_partial_and_blocks_approval() -> None:
    policy = ReviewPolicy(allow_approve=True)
    draft = review_pull_request(
        Source({"pkg/util.py": "y = 1\n"}, fail="list"), REF, policy, cross_file=True
    )
    assert draft.state.run_status == RunStatus.PARTIAL
    assert draft.state.stages["cross_file"] == StageState.FAILED
    assert draft.decision.event == ReviewEvent.COMMENT


def test_it_is_off_unless_asked_and_ignored_for_sources_that_cannot_list_files() -> None:
    plain = review_pull_request(Source(FILES), REF)
    assert plain.findings == () and "cross_file" not in plain.state.stages

    class NoTree:
        get_pull_request = Source.get_pull_request
        list_changed_files = Source.list_changed_files

        def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
            return "y = 1\n"

    draft = review_pull_request(NoTree(), REF, cross_file=True)  # type: ignore[arg-type]
    assert draft.findings == () and "cross_file" not in draft.state.stages
