"""Metrics used by every benchmark. Small samples get wide intervals, never a bare percentage."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. (0, 1) when there are no trials."""
    if total <= 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def fmt_ratio(successes: int, total: int) -> str:
    """'7/10 = 70.0% (95% CI 39.7-89.2%)' or 'n/a (0 cases)'."""
    if total == 0:
        return "n/a (0 cases)"
    lo, hi = wilson_interval(successes, total)
    return f"{successes}/{total} = {100 * successes / total:.1f}% (95% CI {100 * lo:.1f}-{100 * hi:.1f}%)"


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: Confusion) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def precision(self) -> float | None:
        return None if self.tp + self.fp == 0 else self.tp / (self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return None if self.tp + self.fn == 0 else self.tp / (self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    def summary(self) -> str:
        return (
            f"precision {fmt_ratio(self.tp, self.tp + self.fp)}; "
            f"recall {fmt_ratio(self.tp, self.tp + self.fn)}"
        )


Location = tuple[str, int]  # (file path, line)


def within(a: Location, b: Location, tolerance: int) -> bool:
    return a[0] == b[0] and abs(a[1] - b[1]) <= tolerance


def count_matched(
    candidates: Sequence[Location], references: Sequence[Location], tolerance: int
) -> int:
    """How many ``candidates`` have at least one reference on the same file within ``tolerance`` lines."""
    return sum(1 for c in candidates if any(within(c, r, tolerance) for r in references))
