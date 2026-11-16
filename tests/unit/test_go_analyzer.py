"""Go analyser (tree-sitter): every rule fires on risky code and stays quiet on safe code."""

import pytest

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers.go import analyze_go, is_supported, is_test_path
from lyvern.engine.contracts import Category, Origin, Severity
from lyvern.engine.decision import is_blocking
from lyvern.engine.policy import ReviewPolicy


def wrap(body: str) -> str:
    return "package main\n\nfunc f() {\n" + body + "}\n"


def rules(path: str, source: str, **kw: object) -> set[str]:
    return {f.detection_source.split(":")[1] for f in analyze_go(path, source, **kw)}  # type: ignore[arg-type]


POSITIVE = [
    ("tls-verification-off", wrap("\tcfg := &tls.Config{InsecureSkipVerify: true}\n\t_ = cfg\n")),
    ("tls-verification-off", wrap("\tcfg.InsecureSkipVerify = true\n")),
    ("shell-command-injection", wrap('\texec.Command("sh", "-c", "ls "+name)\n')),
    ("shell-command-injection", wrap('\texec.Command("bash", "-c", cmd)\n')),
    (
        "shell-command-injection",
        wrap('\texec.CommandContext(ctx, "sh", "-c", fmt.Sprintf("ls %s", d))\n'),
    ),
    ("sql-string-building", wrap('\tdb.Query("select * from t where n = \'" + name + "\'")\n')),
    (
        "sql-string-building",
        wrap('\tdb.QueryContext(ctx, fmt.Sprintf("select * from t where n = %s", name))\n'),
    ),
    ("sql-string-building", wrap('\tdb.Exec("delete from t where id = " + id)\n')),
    ("weak-hash", wrap("\th := md5.New()\n\t_ = h\n")),
    ("weak-hash", wrap("\tsum := sha1.Sum(data)\n\t_ = sum\n")),
    ("hardcoded-secret", wrap('\tpassword := "hunter2hunter2"\n\t_ = password\n')),
    ("hardcoded-secret", 'package main\n\nconst apiKey = "abcd1234efgh5678"\n'),
    ("hardcoded-secret", wrap('\tcfg := Config{Password: "hunter2hunter2"}\n\t_ = cfg\n')),
    ("secret-token-shape", wrap('\tt := "ghp_' + "a" * 36 + '"\n\t_ = t\n')),
    ("defer-in-loop", wrap("\tfor i := 0; i < 3; i++ {\n\t\tdefer f.Close()\n\t}\n")),
    ("empty-error-branch", wrap("\tif err != nil {\n\t}\n")),
]

NEGATIVE = [
    wrap('\texec.Command("ls", "-la")\n'),  # no shell
    wrap('\texec.Command("sh", "-c", "ls -la")\n'),  # constant command
    wrap('\texec.Command("git", "log", name)\n'),  # arguments are not interpreted by a shell
    wrap('\tdb.Query("select * from t where n = ?", name)\n'),  # placeholder
    wrap('\tdb.Query("select 1")\n'),
    wrap('\tdb.Query("select * from " + "t")\n'),  # constants only
    wrap("\tu := r.URL.Query()\n\t_ = u\n"),  # not a database call
    wrap('\tlog.Printf("%s", name)\n'),
    wrap("\tcfg := &tls.Config{InsecureSkipVerify: false}\n\t_ = cfg\n"),
    wrap("\th := sha256.New()\n\t_ = h\n"),
    wrap('\tpassword := os.Getenv("PASSWORD")\n\t_ = password\n'),
    wrap('\tpassword := "short"\n\t_ = password\n'),
    wrap('\tpassword := "changeme-example-value"\n\t_ = password\n'),
    wrap('\tlabel := "hello world, nothing secret here"\n\t_ = label\n'),
    wrap("\tfor i := 0; i < 3; i++ {\n\t\tfunc() {\n\t\t\tdefer f.Close()\n\t\t}()\n\t}\n"),
    wrap("\tdefer f.Close()\n"),
    wrap("\tif err != nil {\n\t\treturn\n\t}\n"),
    wrap("\tif err != nil {\n\t\t// best effort: the file may not exist\n\t}\n"),
    wrap("\tif x != nil {\n\t}\n"),
]


@pytest.mark.parametrize(("rule", "source"), POSITIVE)
def test_rule_fires(rule: str, source: str) -> None:
    assert rule in rules("svc/main.go", source)


@pytest.mark.parametrize("source", NEGATIVE)
def test_safe_code_is_not_flagged(source: str) -> None:
    assert analyze_go("svc/main.go", source) == []


def test_finding_lines_evidence_and_provenance_are_exact() -> None:
    src = (
        "package main\n\nfunc f() {\n\tcfg := &tls.Config{InsecureSkipVerify: true}\n\t_ = cfg\n}\n"
    )
    (f,) = analyze_go("svc/main.go", src)
    assert (f.line_start, f.line_end) == (4, 4) and "InsecureSkipVerify: true" in f.evidence
    assert f.origin == Origin.STATIC_ANALYSIS and f.category == Category.SECURITY
    assert f.detection_source == "lyvern-go:tls-verification-off" and f.severity == Severity.HIGH


def test_introduced_flag_follows_added_lines() -> None:
    src = "package main\n\nfunc f() {\n\th1 := md5.New()\n\th2 := md5.New()\n\t_, _ = h1, h2\n}\n"
    flags = {f.line_start: f.introduced_by_pr for f in analyze_go("a.go", src, added_lines={5})}
    assert flags == {4: False, 5: True}


def test_security_rules_are_skipped_in_test_files_but_reliability_rules_run() -> None:
    src = wrap("\th := md5.New()\n\t_ = h\n\tif err != nil {\n\t}\n")
    assert rules("svc/main_test.go", src) == {"empty-error-branch"}
    assert rules("svc/testdata/x.go", src) == {"empty-error-branch"}
    assert is_test_path("a/b_test.go") and not is_test_path("a/latest.go")


def test_blocking_follows_confidence_thresholds() -> None:
    src = wrap('\texec.Command("sh", "-c", cmd)\n\tcfg.InsecureSkipVerify = true\n')
    by_rule = {f.detection_source.split(":")[1]: f for f in analyze_go("a.go", src)}
    assert is_blocking(by_rule["tls-verification-off"], ReviewPolicy())  # 0.85
    assert not is_blocking(by_rule["shell-command-injection"], ReviewPolicy())  # 0.75 < 0.8


def test_unsupported_and_broken_input() -> None:
    assert is_supported("a.go") and is_supported("DIR/B.GO") and not is_supported("a.py")
    with pytest.raises(AnalyzerError):
        analyze_go("a.py", "x")
    # a syntax error does not crash the analyser; code that parsed before it is still checked
    broken = "package main\nfunc g() { h := md5.New(); _ = h }\nfunc ((( {\n"
    assert "weak-hash" in rules("a.go", broken)
    assert analyze_go("a.go", "") == []


def test_each_rule_is_reported_once_per_line_and_results_are_sorted() -> None:
    src = wrap("\ta := md5.New(); b := md5.New()\n\tc := md5.New()\n\t_, _, _ = a, b, c\n")
    found = analyze_go("a.go", src)
    assert [f.line_start for f in found] == [4, 5]


def test_unicode_is_safe() -> None:
    src = wrap('\ts := "café ☃"\n\t_ = s\n')
    assert analyze_go("a.go", src) == []
    assert "weak-hash" in rules("a.go", src + "func g() { _ = md5.New() }\n")


def test_false_positives_seen_on_real_code_stay_fixed() -> None:
    # found by scanning a real Go repository: flag-name constants that contain "password"
    flags = (
        'package main\n\nconst (\n\tpassword = "es.password"\n\tapiKeyFile = "es.api-key-file"\n)\n'
    )
    assert analyze_go("cmd/app/flags.go", flags) == []
    env = 'package main\n\nvar m = map[string]string{"JAEGER_PASSWORD": "OTEL_EXPORTER_JAEGER_PASSWORD"}\n'
    assert analyze_go("a.go", env) == []
    assert "hardcoded-secret" in rules(
        "a.go", 'package main\n\nconst password = "hunter2hunter2"\n'
    )


def test_reviewed_lines_marked_for_gosec_are_not_reported() -> None:
    above = wrap("\t// #nosec G402\n\tcfg.InsecureSkipVerify = true\n")
    same = wrap("\tcfg.InsecureSkipVerify = true //nolint:gosec // reviewed\n")
    assert analyze_go("a.go", above) == [] and analyze_go("a.go", same) == []
    # the marker only covers its own line and the next one
    far = wrap("\t// #nosec G402\n\tx := 1\n\t_ = x\n\tcfg.InsecureSkipVerify = true\n")
    assert "tls-verification-off" in rules("a.go", far)
    # it does not silence reliability rules
    assert "empty-error-branch" in rules("a.go", wrap("\t// #nosec\n\tif err != nil {\n\t}\n"))
