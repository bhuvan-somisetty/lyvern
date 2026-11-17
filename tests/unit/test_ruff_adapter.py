"""Ruff adapter: runs the real ruff on small sources."""

import subprocess
from typing import Any

import pytest

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers import ruff as ruff_module
from lyvern.engine.analyzers.ruff import analyze_python, is_test_path
from lyvern.engine.contracts import Category, Origin, Severity
from lyvern.engine.decision import is_blocking
from lyvern.engine.policy import ReviewPolicy

SOURCE = """\
import os


def f(items=[]):
    return eval(items)


print(undefined_name)
"""


def by_source(findings: list[Any]) -> dict[str, Any]:
    return {f.detection_source: f for f in findings}


def test_real_ruff_findings_are_mapped_with_evidence_from_our_own_source() -> None:
    found = by_source(analyze_python("pkg/app.py", SOURCE))
    assert {"ruff:F401", "ruff:B006", "ruff:S307", "ruff:F821"} <= set(found)
    eval_finding = found["ruff:S307"]
    assert eval_finding.category == Category.SECURITY and eval_finding.severity == Severity.HIGH
    assert eval_finding.origin == Origin.STATIC_ANALYSIS
    assert eval_finding.line_start == 5 and "eval(items)" in eval_finding.evidence
    assert found["ruff:F821"].line_start == 8 and "undefined_name" in found["ruff:F821"].evidence
    assert found["ruff:F401"].severity == Severity.LOW


def test_introduced_flag_follows_the_added_lines() -> None:
    found = by_source(analyze_python("app.py", SOURCE, added_lines={8}))
    assert found["ruff:F821"].introduced_by_pr is True
    assert found["ruff:S307"].introduced_by_pr is False  # pre-existing
    assert found["ruff:F401"].introduced_by_pr is False


def test_clean_source_has_no_findings() -> None:
    assert analyze_python("ok.py", "def add(a: int, b: int) -> int:\n    return a + b\n") == []


def test_security_rules_are_skipped_in_test_files_but_bug_rules_are_not() -> None:
    found = by_source(analyze_python("tests/test_app.py", SOURCE))
    assert "ruff:S307" not in found and "ruff:F821" in found
    assert (
        is_test_path("a/tests/x.py")
        and is_test_path("test_x.py")
        and not is_test_path("app/latest.py")
    )


def test_noisy_rules_are_ignored() -> None:
    src = (
        "import random\nimport subprocess\n\nassert 1 == 1\nx = random.random()\n"
        "try:\n    pass\nexcept Exception:\n    pass\n"
    )
    assert not [f for f in analyze_python("a.py", src) if f.detection_source.startswith("ruff:S")]


def test_shell_true_is_reported_but_not_blocking_by_default() -> None:
    src = "import subprocess\n\n\ndef run(cmd):\n    subprocess.call(cmd, shell=True)\n"
    found = by_source(analyze_python("a.py", src))
    assert "ruff:S602" in found
    assert not is_blocking(found["ruff:S602"], ReviewPolicy())  # 0.75 < 0.8 threshold


def test_undefined_name_is_blocking_by_default() -> None:
    (finding,) = [
        f for f in analyze_python("a.py", "print(nope)\n") if f.detection_source == "ruff:F821"
    ]
    assert is_blocking(finding, ReviewPolicy())


def test_syntax_error_is_reported_as_high_severity_bug() -> None:
    findings = analyze_python("broken.py", "def f(:\n    pass\n")
    assert findings, "a file that does not parse must produce a finding"
    assert all(f.category == Category.BUG for f in findings)
    assert any(f.severity == Severity.HIGH for f in findings)


def test_ruff_is_always_run_isolated_with_our_rules_and_no_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Ok:
        returncode = 0
        stdout = b"[]"
        stderr = b""

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured["command"], captured["kwargs"] = command, kwargs
        return Ok()

    monkeypatch.setattr(ruff_module.subprocess, "run", fake_run)
    analyze_python("pkg/a.py", "x = 1\n")
    cmd = captured["command"]
    assert "--isolated" in cmd and "--no-cache" in cmd  # repository config is untrusted
    assert cmd[cmd.index("--select") + 1] == ruff_module.SELECT
    assert cmd[cmd.index("--stdin-filename") + 1] == "pkg/a.py" and cmd[-1] == "-"
    assert captured["kwargs"].get("shell") is not True
    assert captured["kwargs"]["input"] == b"x = 1\n"  # source goes on stdin as bytes, never run
    assert "text" not in captured["kwargs"]  # text mode would rewrite line endings on Windows


def test_unicode_and_crlf_sources_are_handled() -> None:
    src = "def f():\r\n    return nope  # café\r\n"
    assert any(f.detection_source == "ruff:F821" for f in analyze_python("u.py", src))


def test_timeout_and_tool_failure_raise_analyzer_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=1)

    monkeypatch.setattr(ruff_module.subprocess, "run", boom)
    with pytest.raises(AnalyzerError, match="timed out"):
        analyze_python("a.py", "x = 1\n")

    class Bad:
        returncode = 2
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(ruff_module.subprocess, "run", lambda *a, **k: Bad())
    with pytest.raises(AnalyzerError, match="failed"):
        analyze_python("a.py", "x = 1\n")

    class BadJson:
        returncode = 0
        stdout = b"not json"
        stderr = b""

    monkeypatch.setattr(ruff_module.subprocess, "run", lambda *a, **k: BadJson())
    with pytest.raises(AnalyzerError, match="invalid JSON"):
        analyze_python("a.py", "x = 1\n")


def test_line_numbers_are_exact_for_files_with_windows_line_endings() -> None:
    # found on real code: a CRLF file used to reach Ruff with doubled line breaks on Windows,
    # so a finding on line 4 was reported on line 7 and the comment landed on the wrong code
    lf = "import os\nimport sys\n\nprint(sys.argv)\nx = undefined_name\n"
    crlf = lf.replace("\n", "\r\n")
    for source in (lf, crlf):
        found = {(f.detection_source, f.line_start) for f in analyze_python("a.py", source)}
        assert ("ruff:F401", 1) in found and ("ruff:F821", 5) in found
    cr_evidence = [f.evidence for f in analyze_python("a.py", crlf) if f.line_start == 5]
    assert cr_evidence and "x = undefined_name" in cr_evidence[0]
