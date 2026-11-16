"""Features of a pull request that are known when it is opened (no leakage from the review).

Only file names, statuses, line counts, the title, the body length and the author's relationship
to the repository are used. Nothing here reads the code, the review comments or the outcome.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from lyvern.engine.analyzers.deps import is_manifest
from lyvern.github.models import ChangedFileInfo, PullRequestInfo

FEATURE_NAMES: tuple[str, ...] = (
    "log_additions",
    "log_deletions",
    "log_total_churn",
    "log_changed_files",
    "log_max_file_churn",
    "add_share",
    "new_files_share",
    "renamed_files",
    "test_files_share",
    "touches_tests",
    "docs_files_share",
    "docs_only",
    "ci_config_files",
    "dependency_files",
    "migration_files",
    "source_files",
    "n_languages",
    "py_share",
    "jsts_share",
    "go_share",
    "n_top_dirs",
    "max_depth",
    "title_words",
    "title_fix",
    "title_feat",
    "title_docs_or_chore",
    "title_wip",
    "log_body_chars",
    "body_has_checklist",
    "is_draft",
    "assoc_member",
    "assoc_contributor",
    "assoc_first_time",
)

_TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "cypress"}
_DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}
_LOCKS = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "go.sum", "poetry.lock"}
_SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".rs", ".c", ".cc",
    ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".sh",
}  # fmt: skip
_JSTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def _is_test(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name.lower()
    return (
        any(part.lower() in _TEST_PARTS for part in p.parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.go", "_test.py"))
        or ".test." in name
        or ".spec." in name
    )


def _is_doc(path: str) -> bool:
    p = PurePosixPath(path)
    if is_manifest(path):  # requirements.txt is a dependency list, not documentation
        return False
    return p.suffix.lower() in _DOC_SUFFIXES or any(
        part.lower() in {"docs", "doc"} for part in p.parts[:-1]
    )


def _is_ci_config(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name.lower()
    return (
        ".github" in p.parts
        or name in {"dockerfile", "docker-compose.yml", "makefile", "jenkinsfile"}
        or name.startswith("dockerfile")
        or p.suffix.lower() in {".yml", ".yaml"}
    )


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def extract_features(pr: PullRequestInfo, files: Sequence[ChangedFileInfo]) -> dict[str, float]:
    n = len(files)
    additions = sum(f.additions for f in files) if files else pr.additions
    deletions = sum(f.deletions for f in files) if files else pr.deletions
    churn = [f.additions + f.deletions for f in files]
    paths = [f.filename for f in files]
    suffixes = [PurePosixPath(p).suffix.lower() for p in paths]
    source = [s for s in suffixes if s in _SOURCE_SUFFIXES]
    tests = sum(_is_test(p) for p in paths)
    docs = sum(_is_doc(p) for p in paths)
    title = pr.title.strip()
    lowered = title.lower()
    assoc = pr.author_association.upper()
    top_dirs = {
        PurePosixPath(p).parts[0] if len(PurePosixPath(p).parts) > 1 else "." for p in paths
    }

    return {
        "log_additions": math.log1p(additions),
        "log_deletions": math.log1p(deletions),
        "log_total_churn": math.log1p(additions + deletions),
        "log_changed_files": math.log1p(max(n, pr.changed_files)),
        "log_max_file_churn": math.log1p(max(churn, default=0)),
        "add_share": additions / (additions + deletions) if additions + deletions else 0.5,
        "new_files_share": _share(sum(f.status == "added" for f in files), n),
        "renamed_files": float(sum(f.status == "renamed" for f in files)),
        "test_files_share": _share(tests, n),
        "touches_tests": float(tests > 0),
        "docs_files_share": _share(docs, n),
        "docs_only": float(n > 0 and docs == n),
        "ci_config_files": float(sum(_is_ci_config(p) for p in paths)),
        "dependency_files": float(
            sum(is_manifest(p) or PurePosixPath(p).name in _LOCKS for p in paths)
        ),
        "migration_files": float(
            sum("migrat" in p.lower() or p.lower().endswith(".sql") for p in paths)
        ),
        "source_files": float(len(source)),
        "n_languages": float(len(set(source))),
        "py_share": _share(sum(s == ".py" for s in suffixes), n),
        "jsts_share": _share(sum(s in _JSTS for s in suffixes), n),
        "go_share": _share(sum(s == ".go" for s in suffixes), n),
        "n_top_dirs": float(len(top_dirs)),
        "max_depth": float(max((len(PurePosixPath(p).parts) for p in paths), default=0)),
        "title_words": float(len(title.split())),
        "title_fix": float(bool(re.match(r"^(fix|bug|hotfix)\b", lowered))),
        "title_feat": float(bool(re.match(r"^(feat|feature|add|implement)\b", lowered))),
        "title_docs_or_chore": float(
            bool(re.match(r"^(docs?|chore|ci|build|style|typo|bump)\b", lowered))
        ),
        "title_wip": float(bool(re.search(r"\b(wip|draft)\b", lowered)) or pr.draft),
        "log_body_chars": math.log1p(len(pr.body or "")),
        "body_has_checklist": float(bool(re.search(r"- \[[ xX]\]", pr.body or ""))),
        "is_draft": float(pr.draft),
        "assoc_member": float(assoc in {"OWNER", "MEMBER", "COLLABORATOR"}),
        "assoc_contributor": float(assoc == "CONTRIBUTOR"),
        "assoc_first_time": float(assoc in {"FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER"}),
    }
