"""Regressions from the first evaluation on code the analysers had never seen."""

from __future__ import annotations

from lyvern.engine.analyzers.js_ts import analyze_js_ts
from lyvern.engine.analyzers.ruff import analyze_python

REEXPORTS = "\n".join(
    f"from os.path import {n}" for n in ("join", "split", "exists", "isdir", "isfile")
)


def sources(findings: list) -> list[str]:  # type: ignore[type-arg]
    return [f.detection_source for f in findings]


def test_unused_imports_in_an_init_module_are_re_exports() -> None:
    assert "ruff:F401" not in sources(analyze_python("pkg/__init__.py", "import os\n"))


def test_many_unused_imports_in_one_file_are_a_re_export_module() -> None:
    assert "ruff:F401" not in sources(analyze_python("pkg/compat.py", REEXPORTS + "\n"))


def test_a_single_unused_import_is_still_reported() -> None:
    assert "ruff:F401" in sources(analyze_python("pkg/util.py", "import os\n"))


def test_attribute_access_as_a_statement_is_not_reported_but_a_dead_expression_is() -> None:
    code = "def f(response, a):\n    response.content\n    [a]\n"
    found = [f for f in analyze_python("pkg/x.py", code) if f.detection_source == "ruff:B018"]
    assert [f.line_start for f in found] == [3]


def test_constant_setattr_and_startfile_style_rules_are_off() -> None:
    code = "import os\n\n\ndef f(o, url):\n    setattr(o, 'x', 1)\n    os.startfile(url)\n"
    assert not {"ruff:B010", "ruff:S606"} & set(sources(analyze_python("pkg/x.py", code)))


def test_ts_ignore_with_a_reason_is_accepted_and_a_bare_one_is_not() -> None:
    reasoned = "// @ts-ignore - type only exists in newer node typings\nconst a = 1;\n"
    bare = "// @ts-ignore\nconst a = 1;\n"
    nocheck = "// @ts-nocheck legacy file we have not typed yet at all\nconst a = 1;\n"
    assert "lyvern-js:ts-suppress" not in sources(analyze_js_ts("a.ts", reasoned))
    assert "lyvern-js:ts-suppress" in sources(analyze_js_ts("a.ts", bare))
    assert "lyvern-js:ts-suppress" in sources(analyze_js_ts("a.ts", nocheck))


def test_security_rules_skip_benchmark_and_example_code() -> None:
    code = "const a = { rejectUnauthorized: false };\n"
    assert analyze_js_ts("benchmark/index.ts", code) == []
    assert analyze_js_ts("examples/demo.ts", code) == []
    assert "lyvern-js:tls-verification-off" in sources(analyze_js_ts("src/client.ts", code))
