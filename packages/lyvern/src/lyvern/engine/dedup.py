"""Duplicate removal, cross-source corroboration, and ranking of findings.

Two findings are the *same issue* when they are in the same file and category and
their line ranges overlap (or they share a fingerprint). Within a cluster:

* findings from the same detection source are duplicates: keep the best one;
* findings from different detection sources corroborate each other: the survivor
  records the other sources in ``corroborated_by``. That is what lets an LLM
  observation backed by a static-analysis hit become blocking, and nothing else can.
"""

from __future__ import annotations

from collections.abc import Iterable

from lyvern.engine.contracts import Finding, Origin

_TRUSTED = frozenset({Origin.STATIC_ANALYSIS, Origin.HUMAN_CONFIRMED})

# Higher wins when picking the survivor of a cluster. Deterministic evidence beats
# model output; human confirmation beats everything.
_ORIGIN_TRUST = {
    Origin.HUMAN_CONFIRMED: 3,
    Origin.STATIC_ANALYSIS: 2,
    Origin.ML_PREDICTION: 1,
    Origin.LLM_OBSERVATION: 0,
}


def _overlaps(a: Finding, b: Finding) -> bool:
    return a.file_path == b.file_path and a.line_start <= b.line_end and b.line_start <= a.line_end


def _same_issue(a: Finding, b: Finding) -> bool:
    if a.fingerprint == b.fingerprint:
        return True
    return a.category == b.category and _overlaps(a, b)


def _quality(f: Finding) -> tuple[int, int, float, int]:
    return (_ORIGIN_TRUST[f.origin], f.severity.rank, f.confidence, len(f.evidence))


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """Cluster findings about the same issue and return one merged finding per cluster."""
    items = sorted(findings, key=_sort_key)  # deterministic input order
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _same_issue(items[i], items[j]):
                parent[find(j)] = find(i)

    clusters: dict[int, list[Finding]] = {}
    for i, f in enumerate(items):
        clusters.setdefault(find(i), []).append(f)

    merged: list[Finding] = []
    for members in clusters.values():
        ranked = sorted(members, key=_quality, reverse=True)
        best = ranked[0]
        updates: dict[str, object] = {}
        # Only deterministic or human sources count as corroboration. Several LLM or ML
        # outputs agreeing with each other are not independent evidence.
        if best.origin in _TRUSTED:
            sources = {m.detection_source for m in ranked[1:]} - {best.detection_source}
            extra = tuple(sorted(sources | set(best.corroborated_by)))
            if extra != best.corroborated_by:
                updates["corroborated_by"] = extra
        # inherit explanatory text from merged duplicates when the survivor lacks it
        for text_field in ("impact", "recommended_fix"):
            if not getattr(best, text_field):
                donor = next(
                    (getattr(m, text_field) for m in ranked[1:] if getattr(m, text_field)), ""
                )
                if donor:
                    updates[text_field] = donor
        if updates:
            best = Finding.model_validate({**best.model_dump(), **updates})
        merged.append(best)
    return merged


def _sort_key(f: Finding) -> tuple[str, int, int, str, str]:
    return (f.file_path, f.line_start, f.line_end, f.detection_source, f.fingerprint)


def rank(findings: Iterable[Finding]) -> list[Finding]:
    """Most important first: blocking, severity, confidence, then stable location order."""
    return sorted(
        findings,
        key=lambda f: (
            not f.blocking,
            -f.severity.rank,
            -f.confidence,
            f.file_path,
            f.line_start,
            f.fingerprint,
        ),
    )
