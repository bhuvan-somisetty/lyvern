"""Labelled synthetic benchmark for the analysers.

ORIGIN AND LIMITS (read before quoting any number):
* The cases were written by the project author, with expected findings decided from what
  the code does, before running the tools. They are a regression and sanity benchmark, not
  evidence of accuracy on real-world code: the same person wrote the rules and the cases.
* Expected labels are (detection source, line). A finding that is not expected counts as a
  false positive, including an extra finding in a "positive" case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lyvern.benchmark.metrics import Confusion
from lyvern.engine.analyzers.js_ts import analyze_js_ts
from lyvern.engine.analyzers.js_ts import is_supported as is_js_ts
from lyvern.engine.analyzers.ruff import analyze_python

Expected = tuple[str, int]


@dataclass(frozen=True)
class Case:
    case_id: str
    path: str
    source: str
    expected: tuple[Expected, ...] = ()
    note: str = ""


def _py(case_id: str, source: str, *expected: Expected, path: str = "app.py") -> Case:
    return Case(case_id, path, source, tuple(expected))


def _js(case_id: str, source: str, *expected: Expected, path: str = "app.js") -> Case:
    return Case(case_id, path, source, tuple(expected))


CASES: tuple[Case, ...] = (
    # ------------------------------------------------------------- Python: should be flagged
    _py("py-eval", "user_input = input()\nx = eval(user_input)\n", ("ruff:S307", 2)),
    _py("py-exec", "code = input()\nexec(code)\n", ("ruff:S102", 2)),
    _py(
        "py-yaml-load",
        "import yaml\n\ndata = open('f').read()\nconfig = yaml.load(data)\n",
        ("ruff:S506", 4),
    ),
    _py(
        "py-verify-false",
        "import requests\n\nurl = 'https://example.com'\nrequests.get(url, verify=False, timeout=5)\n",
        ("ruff:S501", 4),
    ),
    _py(
        "py-shell-true",
        "import subprocess\n\ncmd = input()\nsubprocess.call(cmd, shell=True)\n",
        ("ruff:S602", 4),
    ),
    _py("py-undefined-name", "print(undefined_name)\n", ("ruff:F821", 1)),
    _py("py-mutable-default", "def f(items=[]):\n    return items\n", ("ruff:B006", 1)),
    _py("py-unused-import", "import os\n", ("ruff:F401", 1)),
    _py(
        "py-pickle",
        "import pickle\n\nblob = input().encode()\nobj = pickle.loads(blob)\n",
        ("ruff:S301", 4),
    ),
    _py(
        "py-md5",
        "import hashlib\n\ndata = b'x'\nh = hashlib.md5(data).hexdigest()\n",
        ("ruff:S324", 4),
    ),
    _py("py-hardcoded-password", "password = 'hunter2hunter2'\n", ("ruff:S105", 1)),
    _py(
        "py-sql-fstring",
        "def q(cur, name):\n    cur.execute(f\"SELECT * FROM t WHERE n = '{name}'\")\n",
        ("ruff:S608", 2),
    ),
    _py("py-syntax-error", "def f(:\n    pass\n", ("ruff:invalid-syntax", 1)),
    _py("py-unused-variable", "def f():\n    x = 1\n", ("ruff:F841", 2)),
    # ------------------------------------------------------------ Python: must stay quiet
    _py("py-ok-json", "import json\n\n\ndef load(s):\n    return json.loads(s)\n"),
    _py("py-ok-subprocess-list", "import subprocess\n\nsubprocess.run(['ls', '-l'], check=True)\n"),
    _py(
        "py-ok-safe-load", "import yaml\n\ndata = open('f').read()\nconfig = yaml.safe_load(data)\n"
    ),
    _py(
        "py-ok-requests",
        "import requests\n\nurl = 'https://example.com'\nrequests.get(url, timeout=5)\n",
    ),
    _py(
        "py-ok-sql-params",
        "def q(cur, name):\n    cur.execute('SELECT * FROM t WHERE n = %s', (name,))\n",
    ),
    _py("py-ok-used-import", "import os\n\nprint(os.getcwd())\n"),
    _py("py-ok-none-default", "def f(items=None):\n    return items or []\n"),
    _py("py-ok-literal-eval", "import ast\n\ntext = input()\nvalue = ast.literal_eval(text)\n"),
    _py("py-ok-sha256", "import hashlib\n\ndata = b'x'\nh = hashlib.sha256(data).hexdigest()\n"),
    _py("py-ok-env-password", "import os\n\npassword = os.environ['PASSWORD']\n"),
    _py("py-ok-sum", "def total(values):\n    return sum(values)\n"),
    _py("py-ok-class", "class A:\n    def m(self) -> int:\n        return 1\n"),
    _py("py-ok-eval-in-tests", "a = input()\nx = eval(a)\n", path="tests/test_calc.py"),
    # ------------------------------------------------------------- JS/TS: should be flagged
    _js("js-eval", "const a = eval(userInput);\n", ("lyvern-js:eval", 1)),
    _js(
        "js-new-function",
        "const f = new Function('return ' + code);\n",
        ("lyvern-js:new-function", 1),
    ),
    _js("js-timer-string", "setTimeout('doThing()', 100);\n", ("lyvern-js:timer-string", 1)),
    _js("js-inner-html", "el.innerHTML = '<b>' + name + '</b>';\n", ("lyvern-js:inner-html", 1)),
    _js("js-outer-html", "el.outerHTML = userHtml;\n", ("lyvern-js:inner-html", 1)),
    _js("js-document-write", "document.write(html);\n", ("lyvern-js:document-write", 1)),
    _js(
        "js-exec-template",
        "child_process.exec(`ls ${dir}`);\n",
        ("lyvern-js:child-process-exec", 1),
    ),
    _js("js-exec-concat", "execSync('ls ' + dir);\n", ("lyvern-js:child-process-exec", 1)),
    _js(
        "js-tls-off",
        "const o = { rejectUnauthorized: false };\n",
        ("lyvern-js:tls-verification-off", 1),
    ),
    _js(
        "js-tls-env",
        "process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';\n",
        ("lyvern-js:tls-env-off", 1),
    ),
    _js("js-api-key", "const apiKey = 'abcd1234efgh5678';\n", ("lyvern-js:hardcoded-secret", 1)),
    _js(
        "js-password-prop",
        "const cfg = { password: 'hunter2hunter2' };\n",
        ("lyvern-js:hardcoded-secret", 1),
    ),
    _js(
        "js-token-shape", "const t = 'ghp_" + "a" * 36 + "';\n", ("lyvern-js:secret-token-shape", 1)
    ),
    _js("js-empty-catch", "try { run(); } catch (e) {}\n", ("lyvern-js:empty-catch", 1)),
    _js("js-debugger", "function f() {\n  debugger;\n}\n", ("lyvern-js:debugger", 2)),
    _js(
        "js-ts-ignore",
        "// @ts-ignore\nconst x: number = 'a';\n",
        ("lyvern-js:ts-suppress", 1),
        path="app.ts",
    ),
    _js(
        "tsx-dangerous-html",
        "export const A = ({x}) => <div dangerouslySetInnerHTML={{__html: x}} />;\n",
        ("lyvern-js:react-dangerous-html", 1),
        path="app.tsx",
    ),
    # ------------------------------------------------------------ JS/TS: must stay quiet
    _js("js-ok-eval-literal", "const a = eval('1 + 1');\n"),
    _js("js-ok-new-function-literal", "const f = new Function('return 1');\n"),
    _js("js-ok-timer-function", "setTimeout(() => run(), 100);\n"),
    _js("js-ok-inner-html-static", "el.innerHTML = '<b>static</b>';\n"),
    _js("js-ok-text-content", "el.textContent = name;\n"),
    _js("js-ok-document-write-literal", "document.write('<p>x</p>');\n"),
    _js("js-ok-regex-exec", "const m = /a(b)/.exec(text);\n"),
    _js("js-ok-exec-constant", "child_process.exec('ls -la');\n"),
    _js("js-ok-tls-on", "const o = { rejectUnauthorized: true };\n"),
    _js("js-ok-env-secret", "const apiKey = process.env.API_KEY;\n"),
    _js("js-ok-short-secret", "const apiKey = 'short';\n"),
    _js("js-ok-placeholder", "const password = 'changeme-example-value';\n"),
    _js("js-ok-catch-handled", "try { run(); } catch (e) { log(e); }\n"),
    _js("js-ok-catch-commented", "try { run(); } catch (e) { /* ignore: best effort */ }\n"),
    _js("js-ok-reduce", "const total = items.reduce((s, i) => s + i, 0);\n"),
    _js("js-ok-eval-in-tests", "eval(x);\n", path="src/a.test.ts"),
    _js(
        "js-ok-story-digest",
        "export const A = { hashedPassword: '" + "ab" * 32 + "' };\n",
        path="a.stories.tsx",
    ),
)


@dataclass
class SyntheticReport:
    overall: Confusion = field(default_factory=Confusion)
    per_source: dict[str, Confusion] = field(default_factory=dict)
    cases: int = 0
    positives: int = 0
    negatives: int = 0
    disagreements: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Synthetic benchmark: {self.cases} cases ({self.positives} with expected findings, "
            f"{self.negatives} that must stay quiet)",
            f"Overall: {self.overall.summary()}",
            "Per detection source:",
        ]
        for name in sorted(self.per_source):
            lines.append(f"  {name}: {self.per_source[name].summary()}")
        if self.disagreements:
            lines.append("Disagreements:")
            lines += [f"  - {d}" for d in self.disagreements]
        else:
            lines.append("Disagreements: none")
        lines.append(
            "Caveat: the author wrote both the rules and these cases; this is a regression check, "
            "not accuracy on real code."
        )
        return "\n".join(lines)


def _analyse(case: Case) -> set[Expected]:
    if is_js_ts(case.path):
        findings = analyze_js_ts(case.path, case.source)
    else:
        findings = analyze_python(case.path, case.source)
    return {(f.detection_source, f.line_start) for f in findings}


def run_synthetic(cases: tuple[Case, ...] = CASES) -> SyntheticReport:
    report = SyntheticReport(cases=len(cases))
    for case in cases:
        expected = set(case.expected)
        found = _analyse(case)
        if expected:
            report.positives += 1
        else:
            report.negatives += 1
        for source, _line in expected | found:
            report.per_source.setdefault(source, Confusion())
        for item in expected & found:
            report.per_source[item[0]].tp += 1
            report.overall.tp += 1
        for item in expected - found:
            report.per_source[item[0]].fn += 1
            report.overall.fn += 1
            report.disagreements.append(f"{case.case_id}: MISSED {item[0]} at line {item[1]}")
        for item in found - expected:
            report.per_source[item[0]].fp += 1
            report.overall.fp += 1
            report.disagreements.append(f"{case.case_id}: UNEXPECTED {item[0]} at line {item[1]}")
    return report
