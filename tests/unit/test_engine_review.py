"""Decision engine, dedup/ranking, placement and rendering."""

import re
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from lyvern.engine.contracts import Category, Finding, Origin, ReviewEvent, RunStatus, Severity
from lyvern.engine.decision import AnalysisState, StageState, decide, is_blocking, mark_blocking
from lyvern.engine.dedup import dedupe, rank
from lyvern.engine.diff import FileStatus, parse_patch
from lyvern.engine.placement import plan_placement
from lyvern.engine.policy import ReviewPolicy
from lyvern.engine.render import (
    extract_fingerprints,
    render_inline,
    render_summary,
)


def mk(**kw: Any) -> Finding:
    base: dict[str, Any] = {
        "category": Category.SECURITY,
        "severity": Severity.HIGH,
        "confidence": 0.9,
        "origin": Origin.STATIC_ANALYSIS,
        "detection_source": "semgrep:py-shell-true",
        "file_path": "app.py",
        "line_start": 10,
        "line_end": 10,
        "title": "Shell injection",
        "description": "subprocess is called with shell=True and user input.",
        "evidence": "subprocess.call(cmd, shell=True)",
        "impact": "Arbitrary command execution.",
        "recommended_fix": "Pass an argument list and drop shell=True.",
    }
    base.update(kw)
    return Finding(**base)


OK_STAGES = {"diff": StageState.COMPLETED, "static_analysis": StageState.COMPLETED}


def good_state(**kw: Any) -> AnalysisState:
    base: dict[str, Any] = {
        "run_status": RunStatus.SUCCEEDED,
        "stages": OK_STAGES,
        "files_total": 3,
        "files_unanalyzed": 0,
        "risk_score": 10,
    }
    base.update(kw)
    return AnalysisState(**base)


APPROVING = ReviewPolicy(allow_approve=True)

# ------------------------------------------------------------------------ contracts


def test_finding_requires_evidence_and_valid_range() -> None:
    with pytest.raises(ValidationError):
        mk(evidence="   ")
    with pytest.raises(ValidationError):
        mk(line_start=5, line_end=4)
    with pytest.raises(ValidationError):
        mk(confidence=1.5)


def test_uncorroborated_llm_or_ml_can_never_be_blocking() -> None:
    with pytest.raises(ValidationError):
        mk(origin=Origin.LLM_OBSERVATION, blocking=True)
    with pytest.raises(ValidationError):
        mk(origin=Origin.ML_PREDICTION, blocking=True)
    ok = mk(origin=Origin.LLM_OBSERVATION, blocking=True, corroborated_by=("semgrep:x",))
    assert ok.blocking


def test_fingerprint_ignores_line_numbers_and_whitespace() -> None:
    a = mk(line_start=10, line_end=10, evidence="x  =  1")
    b = mk(line_start=99, line_end=99, evidence="x = 1", description="different wording")
    c = mk(evidence="y = 2")
    assert a.fingerprint == b.fingerprint != c.fingerprint


# ------------------------------------------------------------------------- decision


def test_no_findings_default_policy_is_comment_not_approve() -> None:
    d = decide([], good_state(), ReviewPolicy())
    assert d.event == ReviewEvent.COMMENT
    assert any("not enabled" in r for r in d.reasons)


def test_clean_run_with_opt_in_approves() -> None:
    d = decide([], good_state(), APPROVING)
    assert d.event == ReviewEvent.APPROVE and d.reasons == () and not d.incomplete


@pytest.mark.parametrize(
    "state",
    [
        good_state(run_status=RunStatus.PARTIAL),
        good_state(stages={"diff": StageState.COMPLETED, "static_analysis": StageState.FAILED}),
        good_state(stages={"diff": StageState.COMPLETED}),
        good_state(stages={**OK_STAGES, "llm": StageState.SKIPPED}),
        good_state(files_unanalyzed=1),
        good_state(risk_score=None),
        good_state(risk_score=80),
        good_state(merge_conflicts=True),
    ],
)
def test_approve_is_blocked_by_any_incomplete_or_risky_state(state: AnalysisState) -> None:
    d = decide([], state, APPROVING)
    assert d.event == ReviewEvent.COMMENT


def test_medium_finding_prevents_approval_but_does_not_block() -> None:
    f = mk(severity=Severity.MEDIUM, category=Category.PERFORMANCE)
    d = decide([f], good_state(), APPROVING)
    assert d.event == ReviewEvent.COMMENT and d.blocking == ()


@pytest.mark.parametrize("severity", list(Severity))
def test_any_finding_even_a_nit_prevents_approval_under_the_default_policy(
    severity: Severity,
) -> None:
    f = mk(severity=severity, confidence=0.3, category=Category.MAINTAINABILITY)
    d = decide([f], good_state(), APPROVING)
    assert d.event != ReviewEvent.APPROVE
    assert any("left to address" in r for r in d.reasons) or d.blocking


def test_an_uncorroborated_ai_observation_also_prevents_approval() -> None:
    f = mk(
        origin=Origin.LLM_OBSERVATION,
        severity=Severity.INFO,
        confidence=0.4,
        detection_source="llm:x",
    )
    assert decide([f], good_state(), APPROVING).event == ReviewEvent.COMMENT


def test_merge_conflicts_prevent_approval_even_with_nothing_else_wrong() -> None:
    d = decide([], good_state(merge_conflicts=True), APPROVING)
    assert d.event == ReviewEvent.COMMENT
    assert any("merge conflicts" in r for r in d.reasons)


def test_confirmed_high_finding_requests_changes() -> None:
    d = decide([mk()], good_state(), ReviewPolicy())
    assert d.event == ReviewEvent.REQUEST_CHANGES and len(d.blocking) == 1


def test_low_confidence_static_finding_does_not_block() -> None:
    assert not is_blocking(mk(confidence=0.5), ReviewPolicy())


def test_pre_existing_finding_does_not_block() -> None:
    assert not is_blocking(mk(introduced_by_pr=False), ReviewPolicy())


def test_uncorroborated_llm_finding_never_blocks_even_if_critical_and_confident() -> None:
    f = mk(origin=Origin.LLM_OBSERVATION, severity=Severity.CRITICAL, confidence=0.99)
    assert not is_blocking(f, ReviewPolicy())
    assert decide([f], good_state(), APPROVING).event == ReviewEvent.COMMENT


def test_corroborated_llm_finding_can_block() -> None:
    f = mk(origin=Origin.LLM_OBSERVATION, corroborated_by=("semgrep:x",))
    assert is_blocking(f, ReviewPolicy())


def test_request_changes_can_be_disabled() -> None:
    d = decide([mk()], good_state(), ReviewPolicy(allow_request_changes=False))
    assert d.event == ReviewEvent.COMMENT and d.wanted == ReviewEvent.REQUEST_CHANGES


def test_failed_run_is_neutral_and_incomplete() -> None:
    d = decide([mk()], good_state(run_status=RunStatus.FAILED), APPROVING)
    assert d.event == ReviewEvent.COMMENT and d.incomplete and d.blocking == ()


def test_superseded_run_publishes_nothing_and_unfinished_run_is_an_error() -> None:
    assert not decide([], good_state(run_status=RunStatus.SUPERSEDED), APPROVING).publish
    with pytest.raises(ValueError):
        decide([], good_state(run_status=RunStatus.RUNNING), APPROVING)


def test_partial_run_with_blocking_finding_still_requests_changes_and_says_incomplete() -> None:
    d = decide([mk()], good_state(run_status=RunStatus.PARTIAL), ReviewPolicy())
    assert d.event == ReviewEvent.REQUEST_CHANGES and d.incomplete


def test_mark_blocking_sets_flag_only_where_eligible() -> None:
    marked = mark_blocking([mk(), mk(confidence=0.4, evidence="other()")], ReviewPolicy())
    assert [f.blocking for f in marked] == [True, False]


finding_st = st.builds(
    mk,
    severity=st.sampled_from(list(Severity)),
    confidence=st.floats(min_value=0, max_value=1),
    origin=st.sampled_from(list(Origin)),
    introduced_by_pr=st.booleans(),
    corroborated_by=st.sampled_from([(), ("other:rule",)]),
    evidence=st.sampled_from(["a", "b", "c"]),
)
stage_st = st.sampled_from(list(StageState))
state_st = st.builds(
    AnalysisState,
    run_status=st.sampled_from(
        [RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.SUPERSEDED]
    ),
    stages=st.fixed_dictionaries({"diff": stage_st, "static_analysis": stage_st, "llm": stage_st}),
    files_total=st.integers(0, 10),
    files_unanalyzed=st.integers(0, 10),
    risk_score=st.none() | st.integers(0, 100),
    merge_conflicts=st.booleans(),
)
policy_st = st.builds(
    ReviewPolicy,
    allow_request_changes=st.booleans(),
    allow_approve=st.booleans(),
    min_confidence_to_block=st.floats(min_value=0, max_value=1),
    max_unanalyzed_share=st.floats(min_value=0, max_value=1),
    approve_max_risk_score=st.integers(0, 100),
)


@settings(max_examples=400, deadline=None)
@given(findings=st.lists(finding_st, max_size=6), state=state_st, policy=policy_st)
def test_decision_invariants_hold_for_arbitrary_inputs(
    findings: list[Finding], state: AnalysisState, policy: ReviewPolicy
) -> None:
    d = decide(findings, state, policy)
    if not d.publish:
        return
    if d.event == ReviewEvent.APPROVE:
        # the safety properties of ED-018
        assert policy.allow_approve
        assert state.run_status == RunStatus.SUCCEEDED
        assert all(s == StageState.COMPLETED for s in state.stages.values())
        assert not d.blocking and not d.incomplete
        assert state.risk_score is not None and state.risk_score <= policy.approve_max_risk_score
        assert state.unanalyzed_share <= policy.max_unanalyzed_share
        assert not state.merge_conflicts
        assert not any(
            f.introduced_by_pr and f.severity.rank >= policy.approve_blocked_by_severity.rank
            for f in findings
        )
    if d.event == ReviewEvent.REQUEST_CHANGES:
        assert d.blocking
        for f in d.blocking:
            assert f.origin in (Origin.STATIC_ANALYSIS, Origin.HUMAN_CONFIRMED) or f.corroborated_by
            assert f.confidence >= policy.min_confidence_to_block and f.introduced_by_pr
    if state.run_status == RunStatus.FAILED:
        assert d.event == ReviewEvent.COMMENT


# ---------------------------------------------------------------------- dedup / rank


def test_same_source_duplicates_collapse() -> None:
    out = dedupe([mk(line_start=10, line_end=12), mk(line_start=11, line_end=11)])
    assert len(out) == 1


def test_static_and_llm_on_same_issue_merge_into_trusted_survivor_with_corroboration() -> None:
    static = mk(impact="", recommended_fix="")
    llm = mk(
        origin=Origin.LLM_OBSERVATION,
        detection_source="llm:model-x",
        evidence="different excerpt",
        impact="Attacker can run commands.",
        recommended_fix="Use shlex and a list.",
    )
    (merged,) = dedupe([llm, static])
    assert merged.origin == Origin.STATIC_ANALYSIS
    assert merged.corroborated_by == ("llm:model-x",)
    assert merged.impact == "Attacker can run commands."  # inherited explanation


def test_two_llm_findings_do_not_corroborate_each_other() -> None:
    a = mk(origin=Origin.LLM_OBSERVATION, detection_source="llm:a", evidence="e1")
    b = mk(origin=Origin.LLM_OBSERVATION, detection_source="llm:b", evidence="e2")
    (merged,) = dedupe([a, b])
    assert merged.corroborated_by == () and not is_blocking(merged, ReviewPolicy())


def test_different_category_or_file_or_distant_lines_stay_separate() -> None:
    items = [
        mk(),
        mk(category=Category.BUG, evidence="b1"),
        mk(file_path="other.py", evidence="b2"),
        mk(line_start=50, line_end=50, evidence="b3"),
    ]
    assert len(dedupe(items)) == 4


def test_dedupe_is_deterministic_regardless_of_input_order() -> None:
    items = [mk(), mk(line_start=40, line_end=41, evidence="z"), mk(file_path="b.py", evidence="q")]
    assert dedupe(items) == dedupe(list(reversed(items)))


def test_rank_orders_blocking_then_severity_then_confidence() -> None:
    low = mk(severity=Severity.LOW, evidence="l")
    high_lowconf = mk(severity=Severity.HIGH, confidence=0.5, evidence="h1")
    high = mk(severity=Severity.HIGH, confidence=0.95, evidence="h2")
    block = mk(severity=Severity.MEDIUM, blocking=True, evidence="m")
    assert rank([low, high_lowconf, high, block]) == [block, high, high_lowconf, low]


# ------------------------------------------------------------------------ placement

PATCH = (
    "@@ -1,4 +1,6 @@\n"
    " import os\n"  # new 1 (context)
    "-old\n"
    "+new_a\n"  # new 2
    "+new_b\n"  # new 3
    "+new_c\n"  # new 4
    " keep\n"  # new 5 (context)
    " end\n"  # new 6 (context)
    "@@ -40,2 +42,3 @@\n"
    " ctx\n"  # new 42
    "+late\n"  # new 43
    " tail\n"  # new 44
)
DIFFS = {"app.py": parse_patch(PATCH, path="app.py")}
POLICY = ReviewPolicy()


def place(*findings: Finding, policy: ReviewPolicy = POLICY) -> Any:
    return plan_placement(list(findings), DIFFS, policy)


def test_finding_on_added_line_is_inline() -> None:
    p = place(mk(line_start=3, line_end=3))
    assert [(c.path, c.line, c.start_line, c.side) for c in p.inline] == [
        ("app.py", 3, None, "RIGHT")
    ]


def test_finding_on_unchanged_context_line_is_not_inline() -> None:
    p = place(mk(line_start=5, line_end=5))
    assert p.inline == () and len(p.general) == 1
    q = place(mk(line_start=5, line_end=5, introduced_by_pr=False))
    assert q.inline == () and q.general == () and len(q.dropped) == 1


def test_line_outside_every_hunk_is_never_inline() -> None:
    p = place(mk(line_start=20, line_end=20))
    assert p.inline == () and len(p.general) == 1


def test_multiline_inside_one_hunk_uses_start_line() -> None:
    p = place(mk(line_start=2, line_end=4))
    assert [(c.start_line, c.line) for c in p.inline] == [(2, 4)]


def test_multiline_across_hunks_anchors_on_first_added_line() -> None:
    p = place(mk(line_start=4, line_end=43))
    assert [(c.start_line, c.line) for c in p.inline] == [(None, 4)]


def test_multiline_range_ends_on_added_lines_even_if_finding_spans_context() -> None:
    # finding covers 1..6: lines 2-4 were added, 1/5/6 are unchanged context
    p = place(mk(line_start=1, line_end=6))
    assert [(c.start_line, c.line) for c in p.inline] == [(2, 4)]
    # finding covers 4..6: only line 4 was added -> single-line comment on 4
    q = place(mk(line_start=4, line_end=6, evidence="other"))
    assert [(c.start_line, c.line) for c in q.inline] == [(None, 4)]


def test_absurd_line_range_is_cheap_and_safe() -> None:
    p = place(mk(line_start=1, line_end=10**9))
    # anchors on the first added block of the first hunk, and finishes instantly
    assert [(c.start_line, c.line) for c in p.inline] == [(2, 4)]


def test_unknown_file_and_deleted_and_binary_files() -> None:
    assert len(place(mk(file_path="nope.py")).general) == 1
    assert len(place(mk(file_path="nope.py", introduced_by_pr=False)).dropped) == 1
    diffs = {
        "gone.py": parse_patch("@@ -1 +0,0 @@\n-x\n", path="gone.py", status=FileStatus.DELETED),
    }
    p = plan_placement([mk(file_path="gone.py", line_start=1, line_end=1)], diffs, POLICY)
    assert p.inline == ()


def test_info_findings_are_general_and_one_comment_per_line_and_limit() -> None:
    info = mk(severity=Severity.INFO, line_start=3, line_end=3, evidence="i")
    assert place(info).inline == () and len(place(info).general) == 1
    a = mk(line_start=3, line_end=3, evidence="a")
    b = mk(line_start=3, line_end=3, evidence="b", category=Category.BUG)
    p = place(a, b)
    assert len(p.inline) == 1 and len(p.general) == 1
    many = [mk(line_start=n, line_end=n, evidence=f"e{n}") for n in (2, 3, 4)]
    q = plan_placement(many, DIFFS, ReviewPolicy(max_inline_comments=2))
    assert len(q.inline) == 2 and len(q.general) == 1


@settings(max_examples=300, deadline=None)
@given(
    start=st.integers(1, 60),
    length=st.integers(0, 60),
    sev=st.sampled_from(list(Severity)),
    introduced=st.booleans(),
)
def test_inline_comments_always_land_on_added_lines(
    start: int, length: int, sev: Severity, introduced: bool
) -> None:
    f = mk(line_start=start, line_end=start + length, severity=sev, introduced_by_pr=introduced)
    p = plan_placement([f], DIFFS, POLICY)
    fd = DIFFS["app.py"]
    for c in p.inline:
        assert fd.is_added(c.line)  # the anchor is always a line this PR added
        if c.start_line is not None:
            assert fd.is_added(c.start_line)
        assert c.line in fd.commentable_lines("RIGHT")
        if c.start_line is not None:
            assert all(n in fd.commentable_lines("RIGHT") for n in range(c.start_line, c.line + 1))
    assert len(p.inline) + len(p.general) + len(p.dropped) == 1  # nothing lost or duplicated


# -------------------------------------------------------------------------- render

EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐✅❌]")


def test_inline_rendering_has_evidence_source_marker_and_no_emoji() -> None:
    text = render_inline(mk(blocking=True))
    assert "HIGH | security" in text and "Evidence:" in text and "subprocess.call" in text
    assert "Source: Static analysis (semgrep:py-shell-true)" in text
    assert "Confidence: 90%" in text and "blocking" in text
    assert extract_fingerprints(text) == {mk().fingerprint}
    assert not EMOJI.search(text)


def test_llm_observation_is_never_presented_as_verified() -> None:
    text = render_inline(mk(origin=Origin.LLM_OBSERVATION, detection_source="llm:m"))
    assert "not independently verified" in text


def test_backticks_in_evidence_cannot_break_out_of_the_code_fence() -> None:
    text = render_inline(mk(evidence="x = '''```\ninjected```'''"))
    fences = re.findall(r"^(`{3,})$", text, flags=re.M)
    assert len(fences) == 2 and len(fences[0]) >= 4


def test_summary_numbers_are_computed_from_the_findings() -> None:
    findings = [
        mk(line_start=3, line_end=3),
        mk(severity=Severity.MEDIUM, line_start=2, line_end=2, evidence="m", category=Category.BUG),
    ]
    placement = plan_placement(findings, DIFFS, POLICY)
    state = good_state(files_total=4, files_unanalyzed=1)
    decision = decide(findings, state, POLICY)
    text = render_summary(
        product_name="Lyvern",
        decision=decision,
        state=state,
        findings=findings,
        placement=placement,
        unanalyzed=[("big.bin", "binary file")],
    )
    assert "Result: Changes requested." in text
    assert "Source files: 4 changed, 3 analyzed, 1 not analyzed." in text
    assert "`big.bin`: binary file" in text
    assert "2 reported (high: 1, medium: 1); 2 inline, 0 general." in text
    assert "does not replace human review" in text and not EMOJI.search(text)


def test_summary_for_approval_says_automated_policy_not_a_person() -> None:
    state = good_state()
    decision = decide([], state, APPROVING)
    text = render_summary(
        product_name="Lyvern",
        decision=decision,
        state=state,
        findings=[],
        placement=plan_placement([], DIFFS, POLICY),
    )
    assert "Approved by automated policy" in text and "not by a person" in text
    assert "Findings: none reported." in text


def test_failed_run_summary_does_not_claim_success() -> None:
    state = good_state(run_status=RunStatus.FAILED, stages={"diff": StageState.FAILED})
    text = render_summary(
        product_name="Lyvern",
        decision=decide([], state, APPROVING),
        state=state,
        findings=[],
        placement=plan_placement([], DIFFS, POLICY),
    )
    assert "could not be completed" in text and "Approved" not in text


def test_summary_is_truncated_to_the_github_limit() -> None:
    many = [
        mk(line_start=1, line_end=1, evidence=f"e{i}", description="d" * 2000, file_path=f"f{i}.py")
        for i in range(60)
    ]
    placement = plan_placement(many, {}, POLICY)
    state = good_state()
    text = render_summary(
        product_name="Lyvern",
        decision=decide(many, state, POLICY),
        state=state,
        findings=many,
        placement=placement,
    )
    assert len(text) <= 60_100 and "truncated" in text
