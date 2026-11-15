"""Unified diff parsing with exact line mapping for GitHub review comments.

Two entry points:

* ``parse_patch``     one file's patch text, as returned by the GitHub "list pull
                      request files" API (starts at the first ``@@`` line).
* ``parse_git_diff``  a complete ``git diff`` with ``diff --git`` file headers.

Hunk boundaries are decided by the line counts in the hunk header, never by line
prefixes, so a removed line whose text is ``-- foo`` (shown as ``--- foo``) or an
added ``++ bar`` cannot be mistaken for a file header. Input that does not add up
raises ``DiffParseError``; callers treat that file as "not analyzed" instead of
guessing line numbers.

GitHub "position": the 0-based index of a line inside the file's patch, where the
first ``@@`` line has index 0 (the line below it is position 1), hunk headers of
later hunks count, and so do ``\\ No newline at end of file`` lines. Review
comments should prefer ``line`` + ``side`` (the modern API); ``position`` is kept
for cross-checking and for older endpoints.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

Side = Literal["LEFT", "RIGHT"]


class DiffParseError(ValueError):
    """The diff is malformed, truncated, or inconsistent with its hunk counts."""


class DiffApplyError(ValueError):
    """A hunk does not match the file it is being applied to."""


class LineKind(StrEnum):
    CONTEXT = "context"
    ADDED = "added"
    DELETED = "deleted"
    NO_NEWLINE = "no_newline"


class FileStatus(StrEnum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    BINARY = "binary"


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    text: str  # without the leading marker character
    old_no: int | None  # 1-based line number in the old file (context, deleted)
    new_no: int | None  # 1-based line number in the new file (context, added)
    index: int  # GitHub "position" of this line within the file's patch


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header_index: int
    section: str
    lines: tuple[DiffLine, ...]


@dataclass(frozen=True)
class FileDiff:
    path: str  # path in the new tree (old path if the file was deleted)
    old_path: str | None
    status: FileStatus
    hunks: tuple[Hunk, ...] = ()
    _by_new: dict[int, DiffLine] = field(default_factory=dict, repr=False, compare=False)
    _by_old: dict[int, DiffLine] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.new_no is not None:
                    self._by_new[line.new_no] = line
                if line.old_no is not None:
                    self._by_old[line.old_no] = line

    @property
    def additions(self) -> int:
        return sum(1 for h in self.hunks for ln in h.lines if ln.kind == LineKind.ADDED)

    @property
    def deletions(self) -> int:
        return sum(1 for h in self.hunks for ln in h.lines if ln.kind == LineKind.DELETED)

    def added_lines(self) -> dict[int, str]:
        """New-file line number -> text, for lines this change added."""
        return {
            ln.new_no: ln.text
            for h in self.hunks
            for ln in h.lines
            if ln.kind == LineKind.ADDED and ln.new_no is not None
        }

    def commentable_lines(self, side: Side = "RIGHT") -> set[int]:
        """Line numbers GitHub accepts for an inline comment on the given side."""
        if side == "RIGHT":
            return set(self._by_new)
        return set(self._by_old)

    def line_at(self, line: int, side: Side = "RIGHT") -> DiffLine | None:
        return (self._by_new if side == "RIGHT" else self._by_old).get(line)

    def position_of(self, line: int, side: Side = "RIGHT") -> int | None:
        found = self.line_at(line, side)
        return None if found is None else found.index

    def is_added(self, line: int) -> bool:
        found = self._by_new.get(line)
        return found is not None and found.kind == LineKind.ADDED


# --------------------------------------------------------------------------- patch


def _split_lines(text: str) -> list[str]:
    # Not str.splitlines(): it also splits on CR, VT, FF, FS/GS/RS, NEL, U+2028 and U+2029,
    # all of which can legitimately occur inside source lines.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_patch(
    patch: str,
    *,
    path: str,
    old_path: str | None = None,
    status: FileStatus = FileStatus.MODIFIED,
) -> FileDiff:
    """Parse the patch of a single file (starting at its first ``@@`` line)."""
    return FileDiff(
        path=path, old_path=old_path, status=status, hunks=_parse_hunks(_split_lines(patch))
    )


def _parse_hunks(lines: Sequence[str]) -> tuple[Hunk, ...]:
    hunks: list[Hunk] = []
    i = 0
    n = len(lines)
    while i < n:
        match = HUNK_RE.match(lines[i])
        if match is None:
            raise DiffParseError(f"expected a hunk header at patch line {i}, got {lines[i]!r}")
        old_start = int(match.group(1))
        old_count = 1 if match.group(2) is None else int(match.group(2))
        new_start = int(match.group(3))
        new_count = 1 if match.group(4) is None else int(match.group(4))
        header_index = i
        i += 1
        old_no, new_no = old_start, new_start
        old_left, new_left = old_count, new_count
        body: list[DiffLine] = []

        while old_left > 0 or new_left > 0:
            if i >= n:
                raise DiffParseError(
                    f"truncated hunk at patch line {header_index}: "
                    f"{old_left} old / {new_left} new lines missing"
                )
            raw = lines[i]
            marker, text = raw[:1], raw[1:]
            if marker == " " or raw == "":  # some tools strip the trailing space of blank context
                if old_left <= 0 or new_left <= 0:
                    raise DiffParseError(f"unexpected context line at patch line {i}")
                body.append(DiffLine(LineKind.CONTEXT, text, old_no, new_no, i))
                old_no, new_no = old_no + 1, new_no + 1
                old_left, new_left = old_left - 1, new_left - 1
            elif marker == "-":
                if old_left <= 0:
                    raise DiffParseError(f"unexpected deleted line at patch line {i}")
                body.append(DiffLine(LineKind.DELETED, text, old_no, None, i))
                old_no, old_left = old_no + 1, old_left - 1
            elif marker == "+":
                if new_left <= 0:
                    raise DiffParseError(f"unexpected added line at patch line {i}")
                body.append(DiffLine(LineKind.ADDED, text, None, new_no, i))
                new_no, new_left = new_no + 1, new_left - 1
            elif marker == "\\":
                body.append(DiffLine(LineKind.NO_NEWLINE, text, None, None, i))
            else:
                raise DiffParseError(f"unrecognized line in hunk at patch line {i}: {raw!r}")
            i += 1

        # a "\ No newline at end of file" marker may follow the last counted line
        while i < n and lines[i].startswith("\\"):
            body.append(DiffLine(LineKind.NO_NEWLINE, lines[i][1:], None, None, i))
            i += 1

        hunks.append(
            Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header_index=header_index,
                section=match.group(5).strip(),
                lines=tuple(body),
            )
        )
    return tuple(hunks)


# ------------------------------------------------------------------------ git diff

_DIFF_HEADER_RE = re.compile(r"^diff --git (.+)$")


def _unquote(path: str) -> str:
    """Decode a path that git wrapped in double quotes (C-style escapes, octal bytes)."""
    if not (len(path) >= 2 and path[0] == '"' and path[-1] == '"'):
        return path
    body = path[1:-1]
    out = bytearray()
    i = 0
    simple = {"n": 10, "t": 9, "r": 13, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12, "v": 11}
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.extend(ch.encode("utf-8"))
            i += 1
            continue
        i += 1
        if i < len(body) and body[i] in simple:
            out.append(simple[body[i]])
            i += 1
        elif i + 3 <= len(body) and body[i : i + 3].isdigit():
            out.append(int(body[i : i + 3], 8))
            i += 3
        else:
            raise DiffParseError(f"bad escape in quoted path {path!r}")
    return out.decode("utf-8", errors="replace")


def _strip_prefix(path: str) -> str:
    path = _unquote(path)
    return path[2:] if path.startswith(("a/", "b/")) else path


def parse_git_diff(text: str) -> list[FileDiff]:
    """Parse a full ``git diff`` (multiple files, renames, binary files, mode changes)."""
    lines = _split_lines(text)
    starts = [i for i, ln in enumerate(lines) if _DIFF_HEADER_RE.match(ln)]
    if not starts:
        if any(ln.strip() for ln in lines):
            raise DiffParseError("no 'diff --git' header found")
        return []
    files: list[FileDiff] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        files.append(_parse_file_block(lines[start:end]))
    return files


def _parse_file_block(block: Sequence[str]) -> FileDiff:
    header = _DIFF_HEADER_RE.match(block[0])
    if header is None:
        raise DiffParseError(f"file block does not start with 'diff --git': {block[0]!r}")
    status = FileStatus.MODIFIED
    old_path: str | None = None
    new_path: str | None = None
    minus: str | None = None
    plus: str | None = None
    binary = False
    first_hunk = len(block)
    for i in range(1, len(block)):
        ln = block[i]
        if HUNK_RE.match(ln):
            first_hunk = i
            break
        if ln.startswith("new file mode"):
            status = FileStatus.ADDED
        elif ln.startswith("deleted file mode"):
            status = FileStatus.DELETED
        elif ln.startswith("rename from "):
            old_path = _unquote(ln[len("rename from ") :])
            status = FileStatus.RENAMED
        elif ln.startswith("rename to "):
            new_path = _unquote(ln[len("rename to ") :])
        elif ln.startswith("--- "):
            minus = ln[4:]
        elif ln.startswith("+++ "):
            plus = ln[4:]
        elif ln.startswith(("Binary files ", "GIT binary patch")):
            binary = True

    if plus is not None and plus != "/dev/null":
        path = _strip_prefix(plus)
    elif minus is not None and minus != "/dev/null":
        path = _strip_prefix(minus)
    elif new_path is not None:
        path = new_path
    else:
        # mode change or binary file: fall back to the "diff --git a/X b/X" header
        rest = header.group(1)
        half = (len(rest) - 1) // 2
        left, right = rest[:half], rest[half + 1 :]
        malformed = rest[half] != " " or _strip_prefix(left) != _strip_prefix(right)
        if malformed and status != FileStatus.RENAMED:
            raise DiffParseError(f"cannot determine file path from {block[0]!r}")
        path = _strip_prefix(right)
    if status == FileStatus.RENAMED and old_path is None and minus not in (None, "/dev/null"):
        old_path = _strip_prefix(minus or "")
    if binary:
        return FileDiff(path=path, old_path=old_path, status=FileStatus.BINARY)
    hunks = _parse_hunks(block[first_hunk:]) if first_hunk < len(block) else ()
    return FileDiff(path=path, old_path=old_path, status=status, hunks=hunks)


# ---------------------------------------------------------------------------- apply


def apply_hunks(old_lines: Sequence[str], hunks: Sequence[Hunk]) -> list[str]:
    """Apply parsed hunks to the old file's lines and return the new file's lines.

    Verifies every context and deleted line against ``old_lines``; raises
    ``DiffApplyError`` on any mismatch. Used to prove the parser correct against
    real ``git diff`` output and to validate fetched file content against a patch.
    """
    out: list[str] = []
    cursor = 0  # index into old_lines of the next unconsumed old line
    for hunk in hunks:
        first_old = hunk.old_start - 1 if hunk.old_count > 0 else hunk.old_start
        if first_old < cursor or first_old > len(old_lines):
            raise DiffApplyError(f"hunk starting at old line {hunk.old_start} is out of order")
        out.extend(old_lines[cursor:first_old])
        cursor = first_old
        for ln in hunk.lines:
            if ln.kind in (LineKind.CONTEXT, LineKind.DELETED):
                if cursor >= len(old_lines) or old_lines[cursor] != ln.text:
                    got = old_lines[cursor] if cursor < len(old_lines) else "<end of file>"
                    raise DiffApplyError(
                        f"old line {cursor + 1} is {got!r}, hunk expects {ln.text!r}"
                    )
                if ln.kind == LineKind.CONTEXT:
                    out.append(ln.text)
                cursor += 1
            elif ln.kind == LineKind.ADDED:
                out.append(ln.text)
    out.extend(old_lines[cursor:])
    return out
