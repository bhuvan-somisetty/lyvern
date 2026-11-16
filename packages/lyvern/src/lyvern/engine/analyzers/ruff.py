"""Ruff adapter (Python).

* The source is passed on stdin and nothing is executed; repository Ruff configuration
  is ignored (``--isolated``) because repository content is untrusted.
* Evidence is read from our own copy of the source, never from the tool's output.
* A curated rule table decides category, severity and confidence. Rules that are noisy
  in a PR review (assert, random, subprocess import/call warnings, try-except-pass) are
  ignored; security rules are not applied to test files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

from lyvern.engine.analyzers.errors import AnalyzerError
from lyvern.engine.contracts import Category, Finding, Origin, Severity

SELECT = "F,E9,B,S,PLE"
IGNORE = "S101,S311,S603,S607,S404,S110,B008,B904"
MAX_EVIDENCE_LINES = 5


@dataclass(frozen=True)
class _Rule:
    category: Category
    severity: Severity
    confidence: float


_C, _S = Category, Severity
_RULES: dict[str, _Rule] = {
    "F821": _Rule(_C.BUG, _S.HIGH, 0.90),  # undefined name
    "F811": _Rule(_C.BUG, _S.MEDIUM, 0.80),  # redefinition of unused name
    "F632": _Rule(_C.BUG, _S.MEDIUM, 0.90),  # `is` comparison with a literal
    "F401": _Rule(_C.MAINTAINABILITY, _S.LOW, 0.90),  # unused import
    "F841": _Rule(_C.MAINTAINABILITY, _S.LOW, 0.80),  # unused variable
    "B006": _Rule(_C.BUG, _S.MEDIUM, 0.90),  # mutable default argument
    "B023": _Rule(_C.BUG, _S.MEDIUM, 0.85),  # closure captures loop variable
    "S102": _Rule(_C.SECURITY, _S.HIGH, 0.80),  # exec
    "S307": _Rule(_C.SECURITY, _S.HIGH, 0.80),  # eval
    "S506": _Rule(_C.SECURITY, _S.HIGH, 0.80),  # unsafe yaml.load
    "S501": _Rule(_C.SECURITY, _S.HIGH, 0.85),  # TLS verification disabled
    "S602": _Rule(_C.SECURITY, _S.HIGH, 0.75),  # shell=True
    "S301": _Rule(_C.SECURITY, _S.MEDIUM, 0.70),  # pickle
    "S324": _Rule(_C.SECURITY, _S.MEDIUM, 0.70),  # weak hash
    "S608": _Rule(_C.SECURITY, _S.MEDIUM, 0.60),  # SQL built from a string
    "S105": _Rule(_C.SECURITY, _S.MEDIUM, 0.60),  # hardcoded password
    "S106": _Rule(_C.SECURITY, _S.MEDIUM, 0.60),
    "S107": _Rule(_C.SECURITY, _S.MEDIUM, 0.60),
}
_PREFIX_DEFAULT: dict[str, _Rule] = {
    "F": _Rule(_C.BUG, _S.MEDIUM, 0.70),
    "B": _Rule(_C.BUG, _S.LOW, 0.60),
    "S": _Rule(_C.SECURITY, _S.LOW, 0.50),
    "PLE": _Rule(_C.BUG, _S.MEDIUM, 0.80),
}
_SYNTAX = _Rule(_C.BUG, _S.HIGH, 0.95)


def is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return (
        any(p in {"tests", "test", "__tests__"} for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", "conftest.py"))
    )


def _rule_for(code: str | None) -> _Rule:
    if code is None or code == "invalid-syntax":  # newer ruff reports syntax errors by name
        return _SYNTAX
    if code in _RULES:
        return _RULES[code]
    if code.startswith("E9"):
        return _SYNTAX
    for prefix in ("PLE", "F", "B", "S"):
        if code.startswith(prefix):
            return _PREFIX_DEFAULT[prefix]
    return _Rule(_C.MAINTAINABILITY, _S.INFO, 0.5)


def _run_ruff(path: str, source: str, timeout: float) -> list[dict[str, object]]:
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--isolated",
        "--no-cache",
        "--select",
        SELECT,
        "--ignore",
        IGNORE,
        "--output-format",
        "json",
        "--stdin-filename",
        path,
        "-",
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, input on stdin
            command,
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AnalyzerError(f"ruff timed out after {timeout:.0f}s") from error
    except OSError as error:
        raise AnalyzerError(f"ruff could not start: {error}") from error
    if proc.returncode not in (0, 1):
        raise AnalyzerError(f"ruff failed (exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as error:
        raise AnalyzerError("ruff returned invalid JSON") from error
    if not isinstance(data, list):
        raise AnalyzerError("ruff returned unexpected JSON")
    return data


def analyze_python(
    path: str,
    source: str,
    *,
    added_lines: set[int] | None = None,
    timeout: float = 20.0,
) -> list[Finding]:
    """Findings for one Python file. ``added_lines`` marks which lines the PR added."""
    lines = source.split("\n")
    findings: list[Finding] = []
    skip_security = is_test_path(path)
    for item in _run_ruff(path, source, timeout):
        code = item.get("code")
        code = code if isinstance(code, str) else None
        if skip_security and code is not None and code.startswith("S"):
            continue
        location = item.get("location") or {}
        end_location = item.get("end_location") or {}
        if not isinstance(location, dict) or not isinstance(end_location, dict):
            continue
        row = location.get("row")
        end_row = end_location.get("row") or row
        if not isinstance(row, int) or not isinstance(end_row, int) or row < 1:
            continue
        end_row = max(end_row, row)
        if row > len(lines):
            continue  # cannot produce evidence from our own copy: do not report
        evidence = "\n".join(lines[row - 1 : min(end_row, row - 1 + MAX_EVIDENCE_LINES)]).rstrip()
        if not evidence.strip():
            evidence = lines[row - 1].rstrip() or "<blank line>"
        rule = _rule_for(code)
        message = str(item.get("message") or "Ruff reported an issue")
        label = code or "syntax-error"
        introduced = (
            True
            if added_lines is None
            else any(n in added_lines for n in range(row, min(end_row, row + 200) + 1))
        )
        url = item.get("url")
        findings.append(
            Finding(
                category=rule.category,
                severity=rule.severity,
                confidence=rule.confidence,
                origin=Origin.STATIC_ANALYSIS,
                detection_source=f"ruff:{label}",
                file_path=path,
                line_start=row,
                line_end=end_row,
                title=f"{label}: {message}"[:200],
                description=message
                + (f" (rule documentation: {url})" if isinstance(url, str) and url else ""),
                evidence=evidence,
                introduced_by_pr=introduced,
            )
        )
    return findings
