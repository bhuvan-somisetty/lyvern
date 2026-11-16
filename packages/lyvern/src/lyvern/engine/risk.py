"""Explainable pull request risk score (0-100). Rule-based, no learned weights.

Every point in the score belongs to a named factor with a plain reason, so a reader can
see exactly why a pull request is rated low, medium, high or critical. This is a triage
aid derived from the change itself, not a prediction of defects: no model has been
trained and no claim of predictive accuracy is made.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from lyvern.engine.contracts import Finding, Severity

_SENSITIVE: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "authentication or authorization code",
        re.compile(r"(auth|login|session|permission|oauth|jwt|acl)", re.I),
    ),
    (
        "secrets, credentials or cryptography",
        re.compile(r"(secret|credential|password|crypto|cipher|token|\.pem$|\.key$)", re.I),
    ),
    ("payment or billing code", re.compile(r"(payment|billing|invoice|checkout|stripe)", re.I)),
    ("database migrations", re.compile(r"(migrations?/|alembic|schema\.sql|\.sql$)", re.I)),
    (
        "CI, build or deployment configuration",
        re.compile(
            r"(\.github/workflows|dockerfile|docker-compose|\.gitlab-ci|jenkinsfile|terraform|helm|k8s|kubernetes)",
            re.I,
        ),
    ),
)
_MANIFESTS = {
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "pyproject.toml",
    "requirements.txt", "uv.lock", "poetry.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock",
    "gemfile", "gemfile.lock", "pom.xml", "build.gradle",
}  # fmt: skip
_SEVERITY_POINTS = {
    Severity.CRITICAL: 15,
    Severity.HIGH: 10,
    Severity.MEDIUM: 4,
    Severity.LOW: 1,
    Severity.INFO: 0,
}
_CAPS = {
    "size": 25,
    "breadth": 12,
    "sensitive": 20,
    "dependencies": 5,
    "tests": 8,
    "findings": 30,
    "unanalyzed": 10,
}


@dataclass(frozen=True)
class RiskFile:
    path: str
    additions: int = 0
    deletions: int = 0
    is_source: bool = True  # False for docs, config and other non-code files


@dataclass(frozen=True)
class RiskFactor:
    name: str
    points: int
    reason: str


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    level: str
    factors: tuple[RiskFactor, ...]

    def explain(self) -> str:
        parts = [f"{f.reason} (+{f.points})" for f in self.factors if f.points > 0]
        return "; ".join(parts) if parts else "no risk factors found"


def _level(score: int) -> str:
    if score < 25:
        return "low"
    if score < 50:
        return "medium"
    if score < 75:
        return "high"
    return "critical"


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    name = p.name.lower()
    return (
        any(part in {"test", "tests", "__tests__", "spec", "e2e"} for part in p.parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", "_test.go"))
        or ".test." in name
        or ".spec." in name
    )


def assess_risk(
    *,
    files: Sequence[RiskFile],
    findings: Sequence[Finding],
    files_total: int,
    files_unanalyzed: int,
) -> RiskAssessment:
    factors: list[RiskFactor] = []

    lines = sum(f.additions + f.deletions for f in files)
    size_points = (
        0
        if lines <= 50
        else 5
        if lines <= 200
        else 12
        if lines <= 500
        else 20
        if lines <= 1000
        else 25
    )
    factors.append(RiskFactor("size", size_points, f"{lines} changed lines"))

    count = len(files)
    breadth_points = 0 if count <= 3 else 4 if count <= 10 else 8 if count <= 25 else 12
    factors.append(RiskFactor("breadth", breadth_points, f"{count} files changed"))

    touched = [label for label, rx in _SENSITIVE if any(rx.search(f.path) for f in files)]
    factors.append(
        RiskFactor(
            "sensitive",
            min(_CAPS["sensitive"], 10 * len(touched)),
            "touches " + ", ".join(touched) if touched else "no sensitive areas touched",
        )
    )

    manifests = [f.path for f in files if PurePosixPath(f.path).name.lower() in _MANIFESTS]
    factors.append(
        RiskFactor(
            "dependencies",
            _CAPS["dependencies"] if manifests else 0,
            "dependency manifest changed" if manifests else "no dependency changes",
        )
    )

    source_added = sum(f.additions for f in files if f.is_source and not is_test_file(f.path))
    tests_touched = any(is_test_file(f.path) for f in files)
    missing_tests = source_added >= 30 and not tests_touched
    factors.append(
        RiskFactor(
            "tests",
            _CAPS["tests"] if missing_tests else 0,
            f"{source_added} source lines added and no test file changed"
            if missing_tests
            else "tests changed or only a small source change",
        )
    )

    introduced = [f for f in findings if f.introduced_by_pr]
    finding_points = min(
        _CAPS["findings"],
        sum(round(_SEVERITY_POINTS[f.severity] * f.confidence) for f in introduced),
    )
    factors.append(
        RiskFactor(
            "findings",
            finding_points,
            f"{len(introduced)} finding(s) introduced by this change"
            if introduced
            else "no findings",
        )
    )

    unanalyzed_points = 0
    if files_total > 0 and files_unanalyzed > 0:
        unanalyzed_points = min(_CAPS["unanalyzed"], round(10 * files_unanalyzed / files_total))
    factors.append(
        RiskFactor(
            "unanalyzed",
            unanalyzed_points,
            f"{files_unanalyzed} of {files_total} source files could not be analysed"
            if unanalyzed_points
            else "all source files analysed",
        )
    )

    score = min(100, sum(f.points for f in factors))
    return RiskAssessment(score=score, level=_level(score), factors=tuple(factors))
