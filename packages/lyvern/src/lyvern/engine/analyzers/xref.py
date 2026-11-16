"""Cross-file check: a symbol this pull request removes is still referenced in another file.

For every top-level function, class or exported name that the diff deletes (and that no added
line defines again, so a move or rename is not flagged), the repository's other files of the same
language are searched at the pull request's head commit for real references: an import of the
name, or a call to it. Each reported reference is confirmed against the file text, not guessed.

Deliberately narrow, to stay trustworthy:

* only top-level definitions (no methods: ``obj.run()`` could belong to any class);
* names of at least 5 characters that are not common words;
* at most 60 files are read per pull request (files next to the definition first);
* generated and vendored directories are skipped.

When the file list or a file cannot be read, ``CrossFileError`` is raised and the review is
marked incomplete instead of silently skipping the check.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from lyvern.engine.analyzers.errors import AnalyzerError
from lyvern.engine.contracts import Category, Finding, Origin, Severity
from lyvern.engine.diff import FileDiff, LineKind

MIN_NAME_LENGTH = 5
MAX_FILES = 60
MAX_SYMBOLS = 8
MAX_REFERENCES_SHOWN = 3
SKIPPED_DIRS = {
    "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__", ".git", "target",
    "third_party", ".next", "coverage",
}  # fmt: skip
COMMON_NAMES = {
    "main", "setup", "teardown", "handler", "handle", "create", "update", "delete", "remove",
    "render", "index", "default", "config", "options", "props", "state", "values", "result",
    "client", "server", "build", "start", "close", "write", "parse", "format", "check", "validate",
    "process", "execute", "output", "input", "number", "string", "object", "array", "length",
    "global", "helper", "helpers", "utils", "types", "error", "errors",
}  # fmt: skip

_PY_DEFS = (
    re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\("),
    re.compile(r"^class\s+([A-Za-z_]\w*)\b"),
)
_JS_DEFS = (
    re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^export\s+(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"),
)
_GO_DEFS = (
    re.compile(r"^func\s+([A-Z]\w*)\s*[\[(]"),  # no receiver: not a method
    re.compile(r"^type\s+([A-Z]\w*)\s"),
)
_GROUPS = {
    ".py": "py",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js", ".mts": "js",
    ".go": "go",
}  # fmt: skip
_DEFS = {"py": _PY_DEFS, "js": _JS_DEFS, "go": _GO_DEFS}


class CrossFileError(AnalyzerError):
    """The repository files could not be listed or read."""


class RepoFiles(Protocol):
    def list_repo_files(self, repo_full_name: str, ref: str) -> list[str]: ...
    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None: ...


@dataclass(frozen=True)
class RemovedSymbol:
    name: str
    path: str
    group: str
    definition: str  # the deleted line
    anchor: int  # a line of the new file next to the deletion (for placement)


def language_group(path: str) -> str | None:
    return _GROUPS.get(PurePosixPath(path).suffix.lower())


def _definition_name(group: str, text: str) -> str | None:
    for pattern in _DEFS[group]:
        match = pattern.match(text)  # top level only: the line must start at column 0
        if match:
            return match.group(1)
    return None


def _usable(name: str, group: str) -> bool:
    if len(name) < MIN_NAME_LENGTH or name.lower() in COMMON_NAMES:
        return False
    return not (group == "py" and name.startswith("_"))


def removed_symbols(diffs: Mapping[str, FileDiff]) -> list[RemovedSymbol]:
    """Top-level definitions the diff deletes and no added line defines again."""
    redefined: set[str] = set()
    for diff in diffs.values():
        group = language_group(diff.path)
        if group is None:
            continue
        for text in diff.added_lines().values():
            name = _definition_name(group, text)
            if name:
                redefined.add(name)

    found: dict[tuple[str, str], RemovedSymbol] = {}
    for diff in diffs.values():
        group = language_group(diff.path)
        if group is None:
            continue
        for hunk in diff.hunks:
            lines = hunk.lines
            for index, line in enumerate(lines):
                if line.kind != LineKind.DELETED:
                    continue
                name = _definition_name(group, line.text)
                if not name or name in redefined or not _usable(name, group):
                    continue
                anchor = next(
                    (ln.new_no for ln in lines[index + 1 :] if ln.new_no is not None),
                    next((ln.new_no for ln in reversed(lines[:index]) if ln.new_no is not None), 1),
                )
                found.setdefault(
                    (diff.path, name),
                    RemovedSymbol(name, diff.path, group, line.text.strip(), anchor or 1),
                )
    return sorted(found.values(), key=lambda s: (s.path, s.name))[:MAX_SYMBOLS]


def _reference_pattern(symbol: RemovedSymbol) -> re.Pattern[str]:
    name = re.escape(symbol.name)
    if symbol.group == "go":
        package = re.escape(PurePosixPath(symbol.path).parent.name or "")
        qualified = rf"\b{package}\.{name}\b|" if package else ""
        return re.compile(rf"{qualified}(?<![\w$.]){name}\s*\(")
    # an import mentioning the name, or a call that is not a method call on something else
    return re.compile(rf"^\s*(?:from\s+\S+\s+)?import\b.*\b{name}\b|(?<![\w$.]){name}\s*\(")


def _is_comment(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(("#", "//", "/*", "*"))


def _candidates(symbol: RemovedSymbol, files: Sequence[str]) -> list[str]:
    home = PurePosixPath(symbol.path).parent.parts

    def closeness(path: str) -> tuple[int, str]:
        parts = PurePosixPath(path).parent.parts
        shared = 0
        for a, b in zip(home, parts, strict=False):
            if a != b:
                break
            shared += 1
        return (-shared, path)

    usable = [
        p
        for p in files
        if p != symbol.path
        and language_group(p) == symbol.group
        and not (set(PurePosixPath(p).parts[:-1]) & SKIPPED_DIRS)
    ]
    return sorted(usable, key=closeness)


def check_removed_symbols(
    source: RepoFiles,
    repo_full_name: str,
    ref: str,
    diffs: Mapping[str, FileDiff],
) -> list[Finding]:
    symbols = removed_symbols(diffs)
    if not symbols:
        return []
    try:
        files = source.list_repo_files(repo_full_name, ref)
    except Exception as error:
        raise CrossFileError(f"could not list repository files ({type(error).__name__})") from None

    texts: dict[str, str | None] = {}
    budget = MAX_FILES
    findings: list[Finding] = []
    for symbol in symbols:
        pattern = _reference_pattern(symbol)
        hits: list[tuple[str, int, str]] = []
        for path in _candidates(symbol, files):
            if path not in texts:
                if budget <= 0:
                    continue
                budget -= 1
                try:
                    texts[path] = source.get_file_text(repo_full_name, path, ref)
                except Exception as error:
                    raise CrossFileError(
                        f"could not read a repository file ({type(error).__name__})"
                    ) from None
            text = texts[path]
            if text is None:
                continue
            for number, line in enumerate(text.split("\n"), start=1):
                if not _is_comment(line) and pattern.search(line):
                    hits.append((path, number, line.strip()[:160]))
                    break  # one reference per file is enough evidence
            if len(hits) >= MAX_REFERENCES_SHOWN:
                break
        if not hits:
            continue
        shown = "\n".join(f"{p}:{n}: {t}" for p, n, t in hits)
        findings.append(
            Finding(
                category=Category.BUG,
                severity=Severity.MEDIUM,
                confidence=0.7,
                origin=Origin.STATIC_ANALYSIS,
                detection_source="lyvern-xref:removed-symbol-still-referenced",
                file_path=symbol.path,
                line_start=symbol.anchor,
                line_end=symbol.anchor,
                title=f"`{symbol.name}` is removed but still referenced elsewhere",
                description=(
                    f"This change deletes `{symbol.name}` (and defines no replacement with that "
                    f"name), but {len(hits)} other file(s) still import or call it, so they would "
                    "fail at import or at run time."
                ),
                evidence=f"removed: {symbol.definition}\nstill referenced:\n{shown}",
                impact="",
                recommended_fix=(
                    f"Update the remaining references, or keep `{symbol.name}` (or a "
                    "replacement under the same name) in this change."
                ),
                introduced_by_pr=True,
            )
        )
    return findings
