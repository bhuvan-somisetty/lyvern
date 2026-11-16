"""Render review text. Plain markdown, no emojis, every number computed from real data.

Origins stay visible: an AI-generated observation is never described as a verified
defect, and a static-analysis hit is attributed to its tool and rule.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from lyvern.engine.contracts import Finding, Origin, ReviewEvent, Severity
from lyvern.engine.decision import AnalysisState, Decision
from lyvern.engine.placement import Placement
from lyvern.engine.risk import RiskAssessment

MAX_BODY_CHARS = 60_000  # GitHub's limit is 65,536
MAX_EVIDENCE_LINES = 12
MAX_EVIDENCE_CHARS = 900
MARKER_PREFIX = "lyvern:fp="

_ORIGIN_LABEL = {
    Origin.STATIC_ANALYSIS: "Static analysis",
    Origin.ML_PREDICTION: "ML prediction (statistical, not verified)",
    Origin.LLM_OBSERVATION: "AI-generated observation (not independently verified)",
    Origin.HUMAN_CONFIRMED: "Confirmed by a reviewer",
}
_EVENT_HEADLINE = {
    ReviewEvent.REQUEST_CHANGES: "Changes requested",
    ReviewEvent.APPROVE: "Approved by automated policy",
    ReviewEvent.COMMENT: "Comment only",
}


def fingerprint_marker(finding: Finding) -> str:
    """Hidden marker so a later run can recognise (and not repeat) its own comment."""
    return f"<!-- {MARKER_PREFIX}{finding.fingerprint} -->"


def extract_fingerprints(body: str) -> set[str]:
    return set(re.findall(rf"<!-- {re.escape(MARKER_PREFIX)}([0-9a-f]+) -->", body))


def _fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _clip_evidence(evidence: str) -> str:
    lines = evidence.strip("\n").split("\n")
    clipped = len(lines) > MAX_EVIDENCE_LINES
    text = "\n".join(lines[:MAX_EVIDENCE_LINES])
    if len(text) > MAX_EVIDENCE_CHARS:
        text, clipped = text[:MAX_EVIDENCE_CHARS], True
    return text + ("\n..." if clipped else "")


def render_inline(finding: Finding) -> str:
    evidence = _clip_evidence(finding.evidence)
    fence = _fence(evidence)
    parts = [
        f"**{finding.severity.value.upper()} | {finding.category.value}** - {finding.title}",
        "",
        finding.description.strip(),
    ]
    if finding.impact.strip():
        parts += ["", f"Why it matters: {finding.impact.strip()}"]
    if finding.recommended_fix.strip():
        parts += ["", f"Suggested fix: {finding.recommended_fix.strip()}"]
    parts += ["", "Evidence:", f"{fence}\n{evidence}\n{fence}"]
    meta = (
        f"Source: {_ORIGIN_LABEL[finding.origin]} ({finding.detection_source}). "
        f"Confidence: {round(finding.confidence * 100)}%."
    )
    if finding.blocking:
        meta += " This finding is blocking."
    if finding.corroborated_by:
        meta += " Also reported by: " + ", ".join(finding.corroborated_by) + "."
    parts += ["", meta, "", fingerprint_marker(finding)]
    return "\n".join(parts)


def _severity_line(findings: Sequence[Finding]) -> str:
    counts = Counter(f.severity for f in findings)
    return ", ".join(f"{s.value}: {counts[s]}" for s in Severity if counts[s])


def _general_item(finding: Finding, reason: str) -> str:
    loc = (
        f"{finding.file_path}:{finding.line_start}"
        if finding.line_start == finding.line_end
        else f"{finding.file_path}:{finding.line_start}-{finding.line_end}"
    )
    text = f"- **{finding.severity.value.upper()} | {finding.category.value}** `{loc}` - "
    text += f"{finding.title}. {finding.description.strip()}"
    if finding.recommended_fix.strip():
        text += f" Suggested fix: {finding.recommended_fix.strip()}"
    text += f" ({_ORIGIN_LABEL[finding.origin]}; {reason}.)"
    return text + f" {fingerprint_marker(finding)}"


def render_summary(
    *,
    product_name: str,
    decision: Decision,
    state: AnalysisState,
    findings: Sequence[Finding],
    placement: Placement,
    unanalyzed: Sequence[tuple[str, str]] = (),
    risk: RiskAssessment | None = None,
) -> str:
    """``findings`` are the findings that survived dedup (not the dropped ones)."""
    published = [c.finding for c in placement.inline] + [g.finding for g in placement.general]
    lines = [
        f"**Automated pull request review ({product_name})**",
        "",
        "This review was generated automatically. It does not replace human review, and "
        "branch protection rules still apply.",
        "",
    ]
    if not decision.publish:
        lines.append("This review was superseded and is not published.")
        return "\n".join(lines)

    if state.run_status.value == "failed":
        lines.append("Result: the review could not be completed.")
    else:
        lines.append(f"Result: {_EVENT_HEADLINE[decision.event]}.")
    for reason in decision.reasons:
        lines.append(f"- {reason}")
    lines.append("")

    analyzed = state.files_total - state.files_unanalyzed
    lines.append(
        f"Source files: {state.files_total} changed, {analyzed} analyzed, "
        f"{state.files_unanalyzed} not analyzed."
    )
    if risk is not None:
        lines.append(f"Risk: {risk.score}/100 ({risk.level}). {risk.explain()}.")
    if unanalyzed:
        lines.append("Not analyzed:")
        for path, why in list(unanalyzed)[:10]:
            lines.append(f"- `{path}`: {why}")
        if len(unanalyzed) > 10:
            lines.append(f"- and {len(unanalyzed) - 10} more")

    if published:
        lines.append("")
        lines.append(
            f"Findings: {len(published)} reported ({_severity_line(published)}); "
            f"{len(placement.inline)} inline, {len(placement.general)} general."
        )
        cats = Counter(f.category.value for f in published)
        lines.append(
            "By category: " + ", ".join(f"{k}: {v}" for k, v in sorted(cats.items())) + "."
        )
    else:
        lines.append("")
        lines.append("Findings: none reported.")
    if placement.dropped:
        lines.append(
            f"{len(placement.dropped)} finding(s) were not reported because they are not "
            "introduced by this pull request."
        )

    if decision.blocking:
        lines += ["", "Blocking findings:"]
        for f in decision.blocking:
            lines.append(f"- `{f.file_path}:{f.line_start}` {f.title}")
    if placement.general:
        lines += ["", "General observations:"]
        lines += [_general_item(g.finding, g.reason) for g in placement.general]

    lines.append("")
    if decision.event == ReviewEvent.REQUEST_CHANGES:
        lines.append(
            "Recommendation: please address the blocking findings and re-run the relevant "
            "tests before merging."
        )
    elif decision.event == ReviewEvent.APPROVE:
        lines.append(
            "No blocking issues were found by the checks configured for this repository. "
            "This approval was issued by automated policy, not by a person."
        )
    else:
        lines.append("Recommendation: review the findings above before merging.")

    body = "\n".join(lines)
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n\n[Review text truncated to fit GitHub's size limit.]"
    return body
