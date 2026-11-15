"""Diff parser tests: hand-written fixtures plus a real-git oracle.

The oracle runs ``git diff --no-index`` on randomly generated file pairs and checks
that applying the parsed hunks to the old file reproduces the new file exactly, and
that every reported line number and GitHub position points at the right text.
"""

import os
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lyvern.engine.diff import (
    DiffApplyError,
    DiffParseError,
    FileStatus,
    LineKind,
    apply_hunks,
    parse_git_diff,
    parse_patch,
)

# ------------------------------------------------------------------ hand-written fixtures

SIMPLE = """\
@@ -1,4 +1,5 @@ def f():
 a
-b
+B
+B2
 c
 d
"""


def test_simple_patch_line_numbers_and_positions() -> None:
    fd = parse_patch(SIMPLE, path="x.py")
    assert fd.additions == 2 and fd.deletions == 1
    assert fd.added_lines() == {2: "B", 3: "B2"}
    # position 0 is the @@ line; the line below it is position 1
    assert fd.position_of(1) == 1  # " a"
    assert fd.position_of(2) == 3  # "+B"  (index: 0 @@, 1 ' a', 2 '-b', 3 '+B')
    assert fd.position_of(3) == 4
    assert fd.commentable_lines("RIGHT") == {1, 2, 3, 4, 5}
    assert fd.commentable_lines("LEFT") == {1, 2, 3, 4}
    assert fd.hunks[0].section == "def f():"
    assert fd.is_added(2) and not fd.is_added(1)


def test_omitted_count_means_one() -> None:
    fd = parse_patch("@@ -3 +3 @@\n-old\n+new\n", path="x")
    assert fd.added_lines() == {3: "new"}
    assert fd.commentable_lines("LEFT") == {3}


def test_new_file_and_deleted_file_hunks() -> None:
    new = parse_patch("@@ -0,0 +1,2 @@\n+one\n+two\n", path="n", status=FileStatus.ADDED)
    assert new.added_lines() == {1: "one", 2: "two"}
    assert new.commentable_lines("LEFT") == set()
    gone = parse_patch("@@ -1,2 +0,0 @@\n-one\n-two\n", path="n", status=FileStatus.DELETED)
    assert gone.additions == 0 and gone.deletions == 2
    assert gone.commentable_lines("RIGHT") == set()
    assert gone.commentable_lines("LEFT") == {1, 2}


def test_multi_hunk_positions_count_later_hunk_headers() -> None:
    patch = "@@ -1,2 +1,2 @@\n a\n-b\n+B\n@@ -10,2 +10,2 @@\n x\n-y\n+Y\n"
    fd = parse_patch(patch, path="x")
    # indexes: 0 @@, 1 ' a', 2 '-b', 3 '+B', 4 @@, 5 ' x', 6 '-y', 7 '+Y'
    assert fd.position_of(2) == 3
    assert fd.position_of(11) == 7
    assert fd.position_of(10) == 5
    assert fd.position_of(5) is None  # between hunks: not commentable


def test_no_newline_marker_is_kept_and_not_counted() -> None:
    patch = (
        "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+B\n\\ No newline at end of file\n"
    )
    fd = parse_patch(patch, path="x")
    kinds = [ln.kind for ln in fd.hunks[0].lines]
    assert kinds.count(LineKind.NO_NEWLINE) == 2
    assert fd.added_lines() == {2: "B"}
    assert fd.position_of(2) == 4  # indexes: 0 @@, 1 ' a', 2 '-b', 3 marker, 4 '+B'


def test_content_that_looks_like_headers_is_not_misparsed() -> None:
    # removed line "-- foo" renders as "--- foo"; added "++ bar" renders as "+++ bar"
    patch = "@@ -1,2 +1,2 @@\n--- foo\n+++ bar\n keep\n"
    # counts say 2 old / 2 new: "--- foo" deleted, "+++ bar" added, " keep" context
    fd = parse_patch(patch, path="x")
    assert [ln.text for ln in fd.hunks[0].lines if ln.kind == LineKind.DELETED] == ["-- foo"]
    assert [ln.text for ln in fd.hunks[0].lines if ln.kind == LineKind.ADDED] == ["++ bar"]


def test_hunk_header_text_inside_content_is_just_content() -> None:
    patch = "@@ -1 +1 @@\n-@@ -9 +9 @@\n+@@ -8 +8 @@\n"
    fd = parse_patch(patch, path="x")
    assert fd.added_lines() == {1: "@@ -8 +8 @@"}


def test_crlf_content_is_preserved() -> None:
    fd = parse_patch("@@ -1 +1 @@\n-a\r\n+b\r\n", path="x")
    assert fd.added_lines() == {1: "b\r"}


@pytest.mark.parametrize(
    "bad",
    [
        "not a hunk\n",
        "@@ -1,3 +1,3 @@\n a\n-b\n",  # truncated
        "@@ -1,1 +1,1 @@\n a\n b\n",  # too many context lines
        "@@ -1,1 +1,1 @@\n+only added\n",  # old side never satisfied
        "@@ -1,1 +1,1 @@\n?weird\n",
    ],
)
def test_malformed_patches_raise(bad: str) -> None:
    with pytest.raises(DiffParseError):
        parse_patch(bad, path="x")


def test_git_diff_multi_file_rename_binary_and_quoted_path() -> None:
    text = (
        "diff --git a/a.py b/a.py\n"
        "index 111..222 100644\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
        "diff --git a/old.txt b/new.txt\n"
        "similarity index 100%\n"
        "rename from old.txt\n"
        "rename to new.txt\n"
        "diff --git a/img.png b/img.png\n"
        "index 1..2 100644\n"
        "Binary files a/img.png and b/img.png differ\n"
        'diff --git "a/sp\\303\\251.txt" "b/sp\\303\\251.txt"\n'
        "new file mode 100644\n"
        "--- /dev/null\n"
        '+++ "b/sp\\303\\251.txt"\n'
        "@@ -0,0 +1 @@\n"
        "+hi\n"
    )
    files = parse_git_diff(text)
    assert [f.path for f in files] == ["a.py", "new.txt", "img.png", "spé.txt"]
    assert files[0].added_lines() == {1: "y"}
    assert files[1].status == FileStatus.RENAMED and files[1].old_path == "old.txt"
    assert files[1].hunks == ()
    assert files[2].status == FileStatus.BINARY
    assert files[3].status == FileStatus.ADDED and files[3].added_lines() == {1: "hi"}


def test_git_diff_empty_and_garbage() -> None:
    assert parse_git_diff("") == []
    with pytest.raises(DiffParseError):
        parse_git_diff("hello world\n")


def test_apply_hunks_detects_mismatch() -> None:
    fd = parse_patch(SIMPLE, path="x")
    assert apply_hunks(["a", "b", "c", "d"], fd.hunks) == ["a", "B", "B2", "c", "d"]
    with pytest.raises(DiffApplyError):
        apply_hunks(["a", "DIFFERENT", "c", "d"], fd.hunks)


# ---------------------------------------------------------------------- real git oracle

TRICKY = [
    "",
    " ",
    "a",
    "b",
    "--",
    "++",
    "-- foo",
    "++ bar",
    "@@ -1 +1 @@",
    "diff --git a/x b/x",
    "\\ No newline at end of file",
    "tab\tinside",
    "café ☃",
    "trailing space ",
    "windows\r",
    "x" * 80,
]
line_st = st.sampled_from(TRICKY) | st.text(
    alphabet=st.characters(blacklist_characters="\n\x00", blacklist_categories=("Cs",)), max_size=12
)
file_st = st.tuples(st.lists(line_st, max_size=25), st.booleans())  # lines, final newline?


def _to_text(lines: list[str], final_newline: bool) -> str:
    return "\n".join(lines) + ("\n" if final_newline and lines else "")


def _to_lines(text: str) -> list[str]:
    out = text.split("\n")
    if out and out[-1] == "":
        out.pop()
    return out


def _git_diff(tmp: Path, old_text: str, new_text: str, context: int) -> str:
    (tmp / "old.txt").write_bytes(old_text.encode("utf-8"))
    (tmp / "new.txt").write_bytes(new_text.encode("utf-8"))
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-color",
            "--no-ext-diff",
            f"-U{context}",
            "old.txt",
            "new.txt",
        ],
        cwd=tmp,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode in (0, 1), proc.stderr.decode(errors="replace")
    return proc.stdout.decode("utf-8")


@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(old=file_st, new=file_st, context=st.sampled_from([0, 1, 3, 10]))
def test_parser_matches_real_git(
    tmp_path: Path, old: tuple[list[str], bool], new: tuple[list[str], bool], context: int
) -> None:
    old_text, new_text = _to_text(*old), _to_text(*new)
    raw = _git_diff(tmp_path, old_text, new_text, context)
    files = parse_git_diff(raw)
    if old_text == new_text:
        assert files == []
        return
    assert len(files) == 1
    fd = files[0]
    old_lines, new_lines = _to_lines(old_text), _to_lines(new_text)

    # 1. applying the parsed hunks to the old file reproduces the new file exactly
    assert apply_hunks(old_lines, fd.hunks) == new_lines

    # 2. line numbers: every added line number holds that exact text in the new file
    for number, text in fd.added_lines().items():
        assert new_lines[number - 1] == text

    # 3. every commentable RIGHT/LEFT line number exists in the respective file
    assert all(1 <= n <= len(new_lines) for n in fd.commentable_lines("RIGHT"))
    assert all(1 <= n <= len(old_lines) for n in fd.commentable_lines("LEFT"))

    # 4. GitHub positions: index of the line inside the file's patch (from the first @@)
    raw_lines = raw.split("\n")
    first = next(i for i, ln in enumerate(raw_lines) if ln.startswith("@@ "))
    for hunk in fd.hunks:
        for ln in hunk.lines:
            raw_line = raw_lines[first + ln.index]
            if ln.kind == LineKind.ADDED:
                assert raw_line == "+" + ln.text
            elif ln.kind == LineKind.DELETED:
                assert raw_line == "-" + ln.text
            elif ln.kind == LineKind.CONTEXT:
                assert raw_line == " " + ln.text
            else:
                assert raw_line.startswith("\\")

    # 5. additions/deletions agree with git's own numstat-style count of the hunks
    assert fd.additions == sum(1 for ln in raw_lines[first:] if _is_added(ln, fd))


def _is_added(raw_line: str, fd: object) -> bool:
    # a "+..." raw line inside the patch region is an added line; the patch region
    # contains no file headers, so no extra filtering is required after the first @@
    return raw_line.startswith("+")


# ------------------------------------------------- realistic edits: few changes in a big file

edit_st = st.lists(
    st.tuples(
        st.sampled_from(["insert", "delete", "replace"]),
        st.integers(min_value=0, max_value=10_000),
        line_st,
    ),
    min_size=1,
    max_size=6,
)


@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    base=st.lists(st.sampled_from(["a", "b", "c", "d", "", "  x", "}"]), min_size=20, max_size=70),
    edits=edit_st,
    final_newline=st.booleans(),
    context=st.sampled_from([0, 1, 3]),
)
def test_parser_matches_real_git_on_sparse_edits(
    tmp_path: Path,
    base: list[str],
    edits: list[tuple[str, int, str]],
    final_newline: bool,
    context: int,
) -> None:
    new = list(base)
    for action, where, text in edits:
        pos = where % (len(new) + 1)
        if action == "insert":
            new.insert(pos, text)
        elif action == "delete" and new:
            del new[pos % len(new)]
        elif new:
            new[pos % len(new)] = text
    old_text, new_text = _to_text(base, final_newline), _to_text(new, final_newline)
    raw = _git_diff(tmp_path, old_text, new_text, context)
    files = parse_git_diff(raw)
    if old_text == new_text:
        assert files == []
        return
    fd = files[0]
    assert apply_hunks(_to_lines(old_text), fd.hunks) == _to_lines(new_text)
    for number, text in fd.added_lines().items():
        assert _to_lines(new_text)[number - 1] == text
