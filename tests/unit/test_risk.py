"""Explainable risk score."""

from hypothesis import given
from hypothesis import strategies as st

from lyvern.engine.contracts import Category, Finding, Origin, Severity
from lyvern.engine.risk import RiskFile, assess_risk, is_test_file


def finding(
    sev: Severity = Severity.HIGH, conf: float = 1.0, introduced: bool = True, n: int = 0
) -> Finding:
    return Finding(
        category=Category.BUG, severity=sev, confidence=conf, origin=Origin.STATIC_ANALYSIS,
        detection_source="t", file_path="a.py", line_start=1, line_end=1, title="t",
        description="d", evidence=f"e{n}", introduced_by_pr=introduced,
    )  # fmt: skip


def risk(files: list[RiskFile], findings: list[Finding] | None = None, total: int = 1, un: int = 0):  # type: ignore[no-untyped-def]
    return assess_risk(files=files, findings=findings or [], files_total=total, files_unanalyzed=un)


def test_tiny_change_is_low_risk_with_explained_zero_factors() -> None:
    r = risk([RiskFile("a.py", 3, 1)])
    assert (r.score, r.level) == (0, "low") and r.explain() == "no risk factors found"


def test_size_and_breadth_tiers() -> None:
    assert (
        risk([RiskFile("a.py", 100, 0)]).score == 5 + 8
    )  # size tier + no tests for 100 source lines
    assert risk([RiskFile("a.py", 300, 0)]).score == 12 + 8  # size + no tests for 300 source lines
    many = [RiskFile(f"f{i}.py", 1, 0) for i in range(11)]
    assert {x.name: x.points for x in risk(many).factors}["breadth"] == 8


def test_sensitive_areas_and_dependency_files_add_named_points() -> None:
    r = risk([RiskFile("src/auth/login.py", 5, 0), RiskFile("package.json", 2, 0)])
    named = {x.name: x for x in r.factors}
    assert named["sensitive"].points == 10 and "authentication" in named["sensitive"].reason
    assert named["dependencies"].points == 5
    two = risk(
        [
            RiskFile("auth.py", 1, 0),
            RiskFile("migrations/001.sql", 1, 0),
            RiskFile("Dockerfile", 1, 0),
        ]
    )
    assert {x.name: x.points for x in two.factors}["sensitive"] == 20  # capped at 2 areas' worth


def test_missing_tests_only_counts_for_real_source_changes() -> None:
    assert {x.name: x.points for x in risk([RiskFile("a.py", 40, 0)]).factors}["tests"] == 8
    with_tests = risk([RiskFile("a.py", 40, 0), RiskFile("tests/test_a.py", 10, 0)])
    assert {x.name: x.points for x in with_tests.factors}["tests"] == 0
    docs = risk([RiskFile("README.md", 200, 0, is_source=False)])
    assert {x.name: x.points for x in docs.factors}["tests"] == 0
    assert (
        is_test_file("src/a.test.ts")
        and is_test_file("pkg/tests/x.py")
        and not is_test_file("src/latest.py")
    )


def test_findings_are_weighted_by_severity_and_confidence_and_pre_existing_are_ignored() -> None:
    points = lambda r: {x.name: x.points for x in r.factors}["findings"]  # noqa: E731
    assert points(risk([RiskFile("a.py", 1, 0)], [finding(Severity.HIGH, 1.0)])) == 10
    assert points(risk([RiskFile("a.py", 1, 0)], [finding(Severity.HIGH, 0.5)])) == 5
    assert points(risk([RiskFile("a.py", 1, 0)], [finding(introduced=False)])) == 0
    many = [finding(Severity.CRITICAL, 1.0, n=i) for i in range(5)]
    assert points(risk([RiskFile("a.py", 1, 0)], many)) == 30  # capped


def test_unanalysed_share_adds_uncertainty() -> None:
    r = risk([RiskFile("a.py", 1, 0)], total=4, un=2)
    assert {x.name: x.points for x in r.factors}["unanalyzed"] == 5


def test_levels_cover_the_scale_and_score_is_capped() -> None:
    worst = risk(
        [RiskFile(f"auth/migrations/Dockerfile{i}.py", 100, 100) for i in range(30)]
        + [RiskFile("package.json", 1, 0)],
        [finding(Severity.CRITICAL, 1.0, n=i) for i in range(5)],
        total=10, un=10,
    )  # fmt: skip
    assert worst.score == 100 and worst.level == "critical"
    assert risk([RiskFile("a.py", 300, 0)]).level == "low"  # 20 < 25


@given(
    adds=st.lists(st.integers(0, 600), min_size=1, max_size=30),
    sev=st.sampled_from(list(Severity)),
    conf=st.floats(0, 1),
)
def test_score_is_bounded_explained_and_monotonic(
    adds: list[int], sev: Severity, conf: float
) -> None:
    files = [RiskFile(f"f{i}.py", a, 0) for i, a in enumerate(adds)]
    base = risk(files)
    worse = risk(files, [finding(sev, conf)])
    assert 0 <= base.score <= 100 and 0 <= worse.score <= 100
    assert worse.score >= base.score  # adding a finding never lowers risk
    assert base.score == min(100, sum(x.points for x in base.factors))
    assert risk(files) == base  # deterministic
