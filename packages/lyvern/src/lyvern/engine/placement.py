"""Decide where each finding is published: inline, general note, or dropped.

Hard rules (never relaxed):

* An inline comment is attached only to a line this PR *added* and that GitHub will
  accept (it is inside a hunk). Never to unchanged lines, never to invented numbers.
* A multi-line inline range runs from the first to the last added line of the finding
  that sit in the same hunk (both ends are added lines); otherwise the comment anchors
  on the first added line of the range.
* A finding that is not introduced by the PR and does not touch a changed line is
  dropped, not reported as a new problem.
* At most one inline comment per line and at most ``max_inline_comments`` per review;
  the rest become general notes so nothing is silently lost.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lyvern.engine.contracts import Finding
from lyvern.engine.diff import FileDiff, FileStatus, Side
from lyvern.engine.policy import ReviewPolicy


@dataclass(frozen=True)
class InlineComment:
    finding: Finding
    path: str
    line: int  # last line of the range (GitHub "line")
    start_line: int | None  # first line for a multi-line comment, else None
    side: Side = "RIGHT"


@dataclass(frozen=True)
class GeneralNote:
    finding: Finding
    reason: str  # why it is not inline


@dataclass(frozen=True)
class Dropped:
    finding: Finding
    reason: str


@dataclass(frozen=True)
class Placement:
    inline: tuple[InlineComment, ...]
    general: tuple[GeneralNote, ...]
    dropped: tuple[Dropped, ...]


MAX_MULTILINE_SPAN = 100  # longer ranges anchor on their first added line


def _anchor(finding: Finding, fd: FileDiff) -> tuple[int, int | None] | None:
    """Return (line, start_line) for an inline comment, or None if no valid anchor exists.

    Work is bounded by the size of the diff, never by the reported line range, so an
    absurd range from a model cannot cause a huge loop.
    """
    start, end = finding.line_start, finding.line_end
    added = sorted(n for n in fd.added_lines() if start <= n <= end)
    if not added:
        return None
    first = added[0]
    hunk_of = {
        ln.new_no: idx for idx, h in enumerate(fd.hunks) for ln in h.lines if ln.new_no is not None
    }
    # Both ends of a multi-line comment are lines this PR added, inside one hunk.
    last = [n for n in added if hunk_of[n] == hunk_of[first]][-1]
    if first < last and last - first + 1 <= MAX_MULTILINE_SPAN:
        return last, first
    return first, None


def plan_placement(
    findings: Sequence[Finding], diffs: Mapping[str, FileDiff], policy: ReviewPolicy
) -> Placement:
    """``findings`` must already be deduplicated and ranked (best first)."""
    inline: list[InlineComment] = []
    general: list[GeneralNote] = []
    dropped: list[Dropped] = []
    used_lines: set[tuple[str, int]] = set()

    for f in findings:
        fd = diffs.get(f.file_path)
        if fd is None:
            if f.introduced_by_pr:
                general.append(GeneralNote(f, "the file is not part of the diff"))
            else:
                dropped.append(Dropped(f, "pre-existing issue in a file this PR does not change"))
            continue

        anchor = None if fd.status in (FileStatus.BINARY, FileStatus.DELETED) else _anchor(f, fd)
        if anchor is None:
            if f.introduced_by_pr:
                general.append(GeneralNote(f, "no changed line in the reported range"))
            else:
                dropped.append(Dropped(f, "pre-existing issue outside the changed lines"))
            continue

        if f.severity.rank < policy.min_severity_for_inline.rank:
            general.append(GeneralNote(f, "below the inline severity threshold"))
            continue
        line, start = anchor
        if (f.file_path, line) in used_lines:
            general.append(GeneralNote(f, "another comment already covers this line"))
            continue
        if len(inline) >= policy.max_inline_comments:
            general.append(GeneralNote(f, "inline comment limit reached"))
            continue
        used_lines.add((f.file_path, line))
        inline.append(InlineComment(f, f.file_path, line, start))

    return Placement(tuple(inline), tuple(general), tuple(dropped))
