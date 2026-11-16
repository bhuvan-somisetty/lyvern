"""Runtime for the pull-request attention model: pure Python, reads a small JSON file.

The model is a standardised logistic regression, exported as plain numbers, so running it needs
no scikit-learn, no pickle and no network. It estimates how likely a human reviewer is to ask for
changes on a pull request that looks like this one. It is advisory: it is never a ``Finding``,
never blocks a merge and never contributes to an approval.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MODEL_PATH = Path(__file__).with_name("attention_model.json")


class ModelFormatError(ValueError):
    pass


@dataclass(frozen=True)
class AttentionEstimate:
    probability: float
    factors: tuple[tuple[str, float], ...]  # (feature, contribution to the log-odds), largest first
    base_rate: float
    heldout_auc: float | None
    trained_on: int


@dataclass(frozen=True)
class AttentionModel:
    feature_names: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coef: tuple[float, ...]
    intercept: float
    meta: Mapping[str, Any]

    @property
    def displayable(self) -> bool:
        """Show the estimate only if the held-out AUC interval excludes chance (0.5)."""
        low = self.meta.get("heldout_auc_ci_low")
        return isinstance(low, int | float) and low > 0.5

    def logit(self, features: Mapping[str, float]) -> float:
        total = self.intercept
        for name, mean, scale, weight in zip(
            self.feature_names, self.mean, self.scale, self.coef, strict=True
        ):
            total += weight * (features.get(name, mean) - mean) / (scale or 1.0)
        return total

    def predict(self, features: Mapping[str, float]) -> float:
        z = self.logit(features)
        return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))

    def estimate(self, features: Mapping[str, float], *, top: int = 3) -> AttentionEstimate:
        contributions = [
            (name, weight * (features.get(name, mean) - mean) / (scale or 1.0))
            for name, mean, scale, weight in zip(
                self.feature_names, self.mean, self.scale, self.coef, strict=True
            )
        ]
        contributions.sort(key=lambda item: abs(item[1]), reverse=True)
        auc = self.meta.get("heldout_auc")
        return AttentionEstimate(
            probability=self.predict(features),
            factors=tuple(contributions[:top]),
            base_rate=float(self.meta.get("base_rate", 0.0)),
            heldout_auc=float(auc) if isinstance(auc, int | float) else None,
            trained_on=int(self.meta.get("n_train_rows", 0)),
        )


def parse_model(data: Mapping[str, Any]) -> AttentionModel:
    try:
        names = tuple(str(n) for n in data["feature_names"])
        mean = tuple(float(v) for v in data["mean"])
        scale = tuple(float(v) for v in data["scale"])
        coef = tuple(float(v) for v in data["coef"])
        intercept = float(data["intercept"])
        meta = dict(data.get("meta", {}))
    except (KeyError, TypeError, ValueError) as error:
        raise ModelFormatError(f"invalid model file: {error}") from error
    if not (len(names) == len(mean) == len(scale) == len(coef)) or not names:
        raise ModelFormatError("invalid model file: lengths do not match")
    if not all(math.isfinite(v) for v in (*mean, *scale, *coef, intercept)):
        raise ModelFormatError("invalid model file: non-finite number")
    return AttentionModel(names, mean, scale, coef, intercept, meta)


def load_model(path: Path | None = None) -> AttentionModel | None:
    """The packaged model, or None if there is none (a fresh checkout before training)."""
    target = path or DEFAULT_MODEL_PATH
    if not target.exists():
        return None
    return parse_model(json.loads(target.read_text(encoding="utf-8")))


_PHRASES = {
    "log_additions": "lines added",
    "log_deletions": "lines deleted",
    "log_total_churn": "size of the change",
    "log_changed_files": "number of files changed",
    "log_max_file_churn": "largest single-file change",
    "add_share": "share of added lines",
    "new_files_share": "share of new files",
    "test_files_share": "share of test files",
    "touches_tests": "tests included",
    "docs_files_share": "share of documentation files",
    "docs_only": "documentation-only change",
    "ci_config_files": "CI or config files",
    "dependency_files": "dependency files",
    "migration_files": "migration or SQL files",
    "source_files": "number of source files",
    "n_languages": "number of languages",
    "n_top_dirs": "number of top-level folders",
    "max_depth": "folder depth",
    "title_words": "title length",
    "log_body_chars": "description length",
    "body_has_checklist": "checklist in the description",
    "assoc_member": "author is a project member",
    "assoc_contributor": "author is an outside contributor",
    "assoc_first_time": "first-time contributor",
}


def render_attention(estimate: AttentionEstimate) -> str:
    """One plain-text line for the review summary. Advisory; never a finding."""
    factors = ", ".join(
        f"{_PHRASES.get(name, name.replace('_', ' '))} ({'raises' if value > 0 else 'lowers'})"
        for name, value in estimate.factors
        if abs(value) >= 0.05
    )
    auc = f", held-out AUC {estimate.heldout_auc:.2f}" if estimate.heldout_auc is not None else ""
    return (
        "Review attention (statistical estimate, advisory): about "
        f"{100 * estimate.probability:.0f}% of pull requests that look like this get line-level "
        f"comments from a person (all pull requests in the training data: "
        f"{100 * estimate.base_rate:.0f}%)."
        + (f" Main factors: {factors}." if factors else "")
        + f" Trained on {estimate.trained_on} public pull requests{auc}; see docs/ML_MODEL_CARD.md."
        " It does not read the code and is not a finding."
    )
