"""JS/TS analyser (tree-sitter): every rule fires on risky code and stays quiet on safe code."""

import pytest

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers.js_ts import analyze_js_ts, is_supported, is_test_path
from lyvern.engine.contracts import Category, Origin, Severity
from lyvern.engine.decision import is_blocking
from lyvern.engine.policy import ReviewPolicy


def rules(path: str, source: str, **kw: object) -> set[str]:
    return {f.detection_source.split(":")[1] for f in analyze_js_ts(path, source, **kw)}  # type: ignore[arg-type]


POSITIVE = [
    ("eval", "const a = eval(userInput);\n"),
    ("new-function", "const f = new Function('return ' + code);\n"),
    ("timer-string", "setTimeout('doThing()', 100);\n"),
    ("timer-string", "setInterval(`tick ${n}`, 100);\n"),
    ("inner-html", "el.innerHTML = '<b>' + name + '</b>';\n"),
    ("inner-html", "el.outerHTML = userHtml;\n"),
    ("document-write", "document.write(html);\n"),
    ("child-process-exec", "child_process.exec(`ls ${dir}`);\n"),
    ("child-process-exec", "execSync('ls ' + dir);\n"),
    ("tls-verification-off", "const o = { rejectUnauthorized: false };\n"),
    ("tls-env-off", "process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';\n"),
    ("hardcoded-secret", "const apiKey = 'abcd1234efgh5678';\n"),
    ("hardcoded-secret", "const cfg = { password: 'hunter2hunter2' };\n"),
    ("secret-token-shape", "const t = 'ghp_" + "a" * 36 + "';\n"),
    ("empty-catch", "try { run(); } catch (e) {}\n"),
    ("debugger", "function f() {\n  debugger;\n}\n"),
    ("ts-suppress", "// @ts-ignore\nconst x: number = 'a';\n"),
]

NEGATIVE = [
    "const a = eval('1 + 1');\n",  # literal argument: nothing user-controlled
    "const f = new Function('return 1');\n",
    "setTimeout(() => run(), 100);\n",
    "el.innerHTML = '<b>static</b>';\n",
    "el.textContent = name;\n",
    "document.write('<p>x</p>');\n",
    "const m = /a(b)/.exec(text);\n",  # RegExp.exec is not child_process
    "child_process.exec('ls -la');\n",  # constant command
    "const o = { rejectUnauthorized: true };\n",
    "const apiKey = process.env.API_KEY;\n",
    "const apiKey = 'short';\n",
    "const password = 'changeme-example-value';\n",
    "const label = 'hello world, nothing secret here';\n",
    "try { run(); } catch (e) { log(e); }\n",
    "try { run(); } catch (e) { /* ignore: best effort */ }\n",
    "// ts-ignore mentioned in prose only\n",
    "const total = items.reduce((s, i) => s + i, 0);\n",
]


@pytest.mark.parametrize(("rule", "source"), POSITIVE)
def test_rule_fires(rule: str, source: str) -> None:
    path = "ts" if rule == "ts-suppress" else "js"
    assert rule in rules(f"src/a.{path}", source)


@pytest.mark.parametrize("source", NEGATIVE)
def test_safe_code_is_not_flagged(source: str) -> None:
    assert analyze_js_ts("src/a.ts", source) == []


def test_jsx_dangerous_html_in_tsx_and_jsx() -> None:
    src = "export const A = ({x}) => <div dangerouslySetInnerHTML={{__html: x}} />;\n"
    assert "react-dangerous-html" in rules("a.tsx", src)
    assert "react-dangerous-html" in rules("a.jsx", src)


def test_finding_lines_evidence_and_provenance_are_exact() -> None:
    src = "const ok = 1;\n\nfunction f(input) {\n  return eval(input);\n}\n"
    (f,) = analyze_js_ts("src/a.js", src)
    assert (f.line_start, f.line_end) == (4, 4) and "return eval(input);" in f.evidence
    assert f.origin == Origin.STATIC_ANALYSIS and f.category == Category.SECURITY
    assert f.detection_source == "lyvern-js:eval" and f.severity == Severity.HIGH


def test_introduced_flag_follows_added_lines() -> None:
    src = "eval(a);\neval(b);\n"
    flags = {f.line_start: f.introduced_by_pr for f in analyze_js_ts("a.js", src, added_lines={2})}
    assert flags == {1: False, 2: True}


def test_security_rules_are_skipped_in_test_files_but_other_rules_run() -> None:
    src = "eval(x);\ndebugger;\n"
    assert rules("src/a.test.ts", src) == {"debugger"}
    assert rules("src/__tests__/a.ts", src) == {"debugger"}
    assert is_test_path("a/b.spec.js") and not is_test_path("src/latest.ts")


def test_blocking_follows_confidence_thresholds() -> None:
    by_rule = {
        f.detection_source.split(":")[1]: f
        for f in analyze_js_ts("a.js", "eval(x);\nexecSync('a' + b);\n")
    }
    assert is_blocking(by_rule["eval"], ReviewPolicy())  # 0.80 meets the 0.8 threshold
    assert not is_blocking(by_rule["child-process-exec"], ReviewPolicy())  # 0.70 does not


def test_unsupported_and_broken_input() -> None:
    assert is_supported("a.ts") and is_supported("a.tsx") and is_supported("a.mjs")
    assert not is_supported("a.go") and not is_supported("a.py")
    with pytest.raises(AnalyzerError):
        analyze_js_ts("a.go", "x")
    # syntax errors do not crash the analyser, and findings elsewhere are still found
    assert "eval" in rules("a.js", "function (((\neval(x);\n")
    assert analyze_js_ts("a.js", "") == []


def test_ts_features_parse_and_unicode_is_safe() -> None:
    src = (
        "interface A { x: number }\n"
        "type B<T> = T extends string ? 1 : 2;\n"
        "enum E { A, B }\n"
        "export async function f<T>(a: A, ...r: T[]): Promise<void> {\n"
        "  const s = 'café ☃';\n"
        "  await Promise.all(r.map(async (v) => v));\n"
        "}\n"
    )
    assert analyze_js_ts("a.ts", src) == []
    assert "eval" in rules("a.ts", src + "eval(s);\n")


def test_each_rule_is_reported_once_per_line_and_results_are_sorted() -> None:
    src = "eval(a); eval(b);\neval(c);\n"
    found = analyze_js_ts("a.js", src)
    assert [f.line_start for f in found] == [1, 2]


def test_false_positives_seen_on_real_code_stay_fixed() -> None:
    # found by scanning real jaeger-ui/jam files: Storybook fixtures holding a digest of "test"
    digest = "da41454ecc40c48499decbca7b1df4595f0a856caada3f182d47293fbad03004"
    story = f"export const A = {{ args: {{ hashedPassword: '{digest}' }} }};\n"
    assert analyze_js_ts("src/stories/Dialog.stories.tsx", story) == []
    assert analyze_js_ts("src/lib/user.ts", story) == []  # a bare hash digest is not a credential
    assert is_test_path("src/stories/Dialog.stories.tsx")
    assert "hardcoded-secret" in rules("src/lib/user.ts", "const password = 'hunter2hunter2';\n")
