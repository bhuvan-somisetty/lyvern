"""Train and honestly evaluate the pull-request attention model (needs scikit-learn).

Protocol, fixed in advance so the test numbers cannot be tuned on:

1. Inside every repository the pull requests are ordered by creation time: the oldest 70% are
   training data, the newest 30% are the test data (the model never sees the future).
2. Model choice (the regularisation strength) uses only the training part, by 5-fold
   cross-validation.
3. The chosen model is evaluated ONCE on the test part and compared with simple baselines
   (always predict the base rate; size of the change only; a gradient-boosted model).
4. A leave-one-repository-out check measures how it does on a repository it has never seen.
5. The model that is shipped is refitted on all rows; the reported numbers are from the step-3
   model that did not see the test rows.

The result is exported as plain numbers (JSON), plus a model card with every figure and its limits.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from lyvern.ml.features import FEATURE_NAMES

MIN_ROWS = 200
TRAIN_FRACTION = 0.7
C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0)
BOOTSTRAPS = 1000


@dataclass
class Dataset:
    repos: list[str]
    created: list[str]
    x: Any  # numpy array (n, features)
    y: Any  # numpy array (n,)


# derived targets: name -> (column, minimum count that counts as a positive)
DERIVED_TARGETS = {
    "inline_feedback": ("human_inline_comments", 1),  # a person left line-level feedback
    "heavy_feedback": ("human_inline_comments", 3),  # three or more such comments
}


TARGET_TEXT = {
    "inline_feedback": (
        "a person other than the author leaves at least one inline code comment",
        "line-level comments from a person",
    ),
    "heavy_feedback": (
        "a person other than the author leaves three or more inline code comments",
        "three or more line-level comments from a person",
    ),
    "changes_requested": (
        "a person other than the author submits a CHANGES_REQUESTED review",
        "a change request from a person",
    ),
}


def describe_target(target: str) -> tuple[str, str]:
    return TARGET_TEXT.get(target, (f"the label `{target}` is 1", f"label `{target}`"))


def column_rate(path: Path, column: str) -> float | None:
    """Share of rows with a positive value in a CSV column, or None if it is not there."""
    total = positive = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                positive += int(float(row[column]) > 0)
            except (KeyError, ValueError):
                return None
            total += 1
    return positive / total if total else None


def label_value(row: dict[str, str], target: str) -> int:
    if target in DERIVED_TARGETS:
        column, minimum = DERIVED_TARGETS[target]
        return int(float(row[column]) >= minimum)
    return int(row[target])


def load_dataset(path: Path, target: str) -> Dataset:
    repos: list[str] = []
    created: list[str] = []
    rows: list[list[float]] = []
    labels: list[int] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append([float(row[name]) for name in FEATURE_NAMES])
                labels.append(label_value(row, target))
            except (KeyError, ValueError):
                continue
            repos.append(row["repo"])
            created.append(row["created_at"])
    if len(rows) < MIN_ROWS:
        raise ValueError(f"need at least {MIN_ROWS} labelled pull requests, found {len(rows)}")
    y = np.array(labels)
    if len(set(labels)) < 2:
        raise ValueError("the target has only one class in the data")
    return Dataset(repos, created, np.array(rows), y)


def temporal_split(data: Dataset, fraction: float = TRAIN_FRACTION) -> tuple[Any, Any]:
    """Boolean masks (train, test): oldest `fraction` of each repository's rows are training."""
    by_repo: dict[str, list[int]] = defaultdict(list)
    for index, repo in enumerate(data.repos):
        by_repo[repo].append(index)
    train = np.zeros(len(data.repos), dtype=bool)
    for indices in by_repo.values():
        ordered = sorted(indices, key=lambda i: data.created[i])
        cut = int(len(ordered) * fraction)
        for i in ordered[:cut]:
            train[i] = True
    return train, ~train


def bootstrap_auc(y: Any, scores: Any, *, seed: int = 0) -> tuple[float, float]:
    from sklearn.metrics import roc_auc_score  # type: ignore[import-untyped]

    rng = np.random.default_rng(seed)
    n = len(y)
    values: list[float] = []
    for _ in range(BOOTSTRAPS):
        pick = rng.integers(0, n, n)
        if len(set(y[pick].tolist())) < 2:
            continue
        values.append(float(roc_auc_score(y[pick], scores[pick])))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def _logreg(c: float) -> Any:
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
    from sklearn.pipeline import make_pipeline  # type: ignore[import-untyped]
    from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=2000))


def _gbm() -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier  # type: ignore[import-untyped]

    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, early_stopping=False, random_state=0
    )


def cross_validated_auc(make_model: Any, x: Any, y: Any, *, seed: int = 0) -> tuple[float, float]:
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold  # type: ignore[import-untyped]

    scores: list[float] = []
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    for fit_idx, val_idx in folds.split(x, y):
        model = make_model()
        model.fit(x[fit_idx], y[fit_idx])
        scores.append(float(roc_auc_score(y[val_idx], model.predict_proba(x[val_idx])[:, 1])))
    return float(np.mean(scores)), float(np.std(scores))


def calibration_table(y: Any, p: Any, bins: int = 5) -> list[tuple[float, float, int]]:
    order = np.argsort(p)
    table: list[tuple[float, float, int]] = []
    for chunk in np.array_split(order, bins):
        if len(chunk):
            table.append((float(p[chunk].mean()), float(y[chunk].mean()), len(chunk)))
    return table


def leave_one_repo_out(data: Dataset, c: float) -> dict[str, float]:
    from sklearn.metrics import roc_auc_score

    results: dict[str, float] = {}
    repos = np.array(data.repos)
    for repo in sorted(set(data.repos)):
        test = repos == repo
        if len(set(data.y[test].tolist())) < 2 or len(set(data.y[~test].tolist())) < 2:
            continue
        model = _logreg(c)
        model.fit(data.x[~test], data.y[~test])
        results[repo] = float(roc_auc_score(data.y[test], model.predict_proba(data.x[test])[:, 1]))
    return results


def train_and_report(data_path: Path, target: str, model_out: Path, card_out: Path) -> str:
    import sklearn  # type: ignore[import-untyped]
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        roc_auc_score,
    )

    data = load_dataset(data_path, target)
    train_mask, test_mask = temporal_split(data)
    x_train, y_train = data.x[train_mask], data.y[train_mask]
    x_test, y_test = data.x[test_mask], data.y[test_mask]
    if len(set(y_train.tolist())) < 2 or len(set(y_test.tolist())) < 2:
        raise ValueError("the train or the test part has only one class; collect more data")

    # ---- model selection on the training part only
    cv = {c: cross_validated_auc(lambda c=c: _logreg(c), x_train, y_train) for c in C_GRID}
    best_c = max(cv, key=lambda c: cv[c][0])
    size_index = [FEATURE_NAMES.index("log_total_churn")]
    size_cv = cross_validated_auc(lambda: _logreg(1.0), x_train[:, size_index], y_train)
    gbm_cv = cross_validated_auc(_gbm, x_train, y_train)

    # ---- one evaluation on the held-out, newest part
    model = _logreg(best_c)
    model.fit(x_train, y_train)
    p_test = model.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(y_test, p_test))
    auc_low, auc_high = bootstrap_auc(y_test, p_test)
    size_model = _logreg(1.0)
    size_model.fit(x_train[:, size_index], y_train)
    size_auc = float(roc_auc_score(y_test, size_model.predict_proba(x_test[:, size_index])[:, 1]))
    gbm = _gbm()
    gbm.fit(x_train, y_train)
    gbm_auc = float(roc_auc_score(y_test, gbm.predict_proba(x_test)[:, 1]))
    base_rate = float(y_train.mean())
    brier = float(brier_score_loss(y_test, p_test))
    brier_base = float(brier_score_loss(y_test, np.full(len(y_test), base_rate)))
    ap = float(average_precision_score(y_test, p_test))
    prevalence_test = float(y_test.mean())
    top_n = max(1, len(p_test) // 5)
    top = np.argsort(-p_test)[:top_n]
    top_precision = float(y_test[top].mean())
    calibration = calibration_table(y_test, p_test)
    loo = leave_one_repo_out(data, best_c)

    # ---- the shipped model: refit on all rows, exported as plain numbers
    final = _logreg(best_c)
    final.fit(data.x, data.y)
    scaler, logreg = final[0], final[1]
    names = list(FEATURE_NAMES)
    coef = [float(v) for v in logreg.coef_[0]]
    meta: dict[str, Any] = {
        "target": target,
        "trained_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "sklearn_version": sklearn.__version__,
        "best_C": best_c,
        "n_train_rows": len(data.y),
        "n_eval_train": int(train_mask.sum()),
        "n_eval_test": int(test_mask.sum()),
        "base_rate": float(data.y.mean()),
        "heldout_auc": auc,
        "heldout_auc_ci_low": auc_low,
        "heldout_auc_ci_high": auc_high,
        "heldout_size_only_auc": size_auc,
        "heldout_gbm_auc": gbm_auc,
        "leave_one_repo_out_auc": loo,
        "repos": sorted(set(data.repos)),
    }
    payload = {
        "feature_names": names,
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) if v else 1.0 for v in scaler.scale_],
        "coef": coef,
        "intercept": float(logreg.intercept_[0]),
        "meta": meta,
    }
    model_out.parent.mkdir(parents=True, exist_ok=True)
    model_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    card = render_card(
        data=data,
        target=target,
        meta=meta,
        cv=cv,
        size_cv=size_cv,
        gbm_cv=gbm_cv,
        prevalence_test=prevalence_test,
        ap=ap,
        brier=brier,
        brier_base=brier_base,
        top_precision=top_precision,
        top_n=top_n,
        calibration=calibration,
        coefficients=sorted(zip(names, coef, strict=True), key=lambda kv: -abs(kv[1])),
        change_request_rate=column_rate(data_path, "changes_requested"),
    )
    card_out.parent.mkdir(parents=True, exist_ok=True)
    card_out.write_text(card, encoding="utf-8")
    return (
        f"rows={len(data.y)} (train {int(train_mask.sum())}, test {int(test_mask.sum())}), "
        f"positive rate {data.y.mean():.1%}\n"
        f"held-out AUC {auc:.3f} (95% CI {auc_low:.3f}-{auc_high:.3f}); size-only {size_auc:.3f}; "
        f"gradient boosting {gbm_auc:.3f}\n"
        f"leave-one-repo-out mean AUC {np.mean(list(loo.values())):.3f} over {len(loo)} repos\n"
        f"model written to {model_out}, card to {card_out}"
    )


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def render_card(
    *,
    data: Dataset,
    target: str,
    meta: dict[str, Any],
    cv: dict[float, tuple[float, float]],
    size_cv: tuple[float, float],
    gbm_cv: tuple[float, float],
    prevalence_test: float,
    ap: float,
    brier: float,
    brier_base: float,
    top_precision: float,
    top_n: int,
    calibration: list[tuple[float, float, int]],
    coefficients: list[tuple[str, float]],
    change_request_rate: float | None = None,
) -> str:
    per_repo = {r: int(sum(1 for x in data.repos if x == r)) for r in sorted(set(data.repos))}
    loo = meta["leave_one_repo_out_auc"]
    definition, _ = describe_target(target)
    gap = meta["heldout_auc"] - meta["heldout_size_only_auc"]
    beats = gap >= 0.02
    cv_mean = max(m for m, _s in cv.values())
    top_bin = calibration[-1] if calibration else None
    overconfident = top_bin is not None and top_bin[0] > 1.5 * max(top_bin[1], 1e-9)
    lines = [
        "# Model card: pull-request attention model",
        "",
        "Generated by `lyvern ml train`. Do not edit by hand; retrain to change it.",
        "",
        "## What it does",
        f"Estimates how likely it is that {definition} on a pull request, using only"
        " facts known when the pull request is opened (size, file types and paths, title, body"
        " length, the author's relationship to the repository). It is **advisory**: it is never a"
        " finding, never blocks a merge and never counts toward an approval. It does not read the"
        " code, so it cannot say whether the code is correct.",
        "",
        "## Data",
        f"- Target: `{target}` = {definition}. Bots are excluded as authors and as reviewers.",
        *(
            [
                f'- Why not "changes requested": only {_pct(change_request_rate)} of these pull'
                " requests received a CHANGES_REQUESTED review (reviewers rarely use that state),"
                " which is too few positives to train or evaluate a model honestly."
            ]
            if change_request_rate is not None and target != "changes_requested"
            else []
        ),
        f"- {len(data.y)} real closed pull requests from {len(per_repo)} public repositories,"
        f" read through the GitHub API with read-only calls: "
        + ", ".join(f"{r} ({n})" for r, n in per_repo.items()),
        f"- Positive rate: {_pct(meta['base_rate'])}.",
        "- Known limits of the labels: repositories differ a lot in review culture (in some,"
        " maintainers merge their own changes without review), so the label is a noisy proxy"
        ' for "needed attention".',
        "",
        "## Method",
        f"- Features ({len(FEATURE_NAMES)}): see `lyvern/ml/features.py`.",
        "- Split: inside each repository the oldest 70% of pull requests train the model and the"
        f" newest 30% test it ({meta['n_eval_train']} train, {meta['n_eval_test']} test).",
        "- Model: standardised logistic regression. The regularisation strength was chosen by"
        f" 5-fold cross-validation on the training part only (C = {meta['best_C']}).",
        "- The shipped model is refitted on all rows; the numbers below come from the model that"
        " did not see the test rows.",
        "",
        "## Results on the held-out newest pull requests (evaluated once)",
        "| Measure | Value |",
        "| --- | --- |",
        f"| AUC (1.0 perfect, 0.5 chance) | {meta['heldout_auc']:.3f}"
        f" (95% bootstrap CI {meta['heldout_auc_ci_low']:.3f}"
        f" to {meta['heldout_auc_ci_high']:.3f}) |",
        f"| Baseline: size of the change only | {meta['heldout_size_only_auc']:.3f} |",
        f"| Comparison: gradient boosting | {meta['heldout_gbm_auc']:.3f} |",
        f"| Positive rate in the test part | {_pct(prevalence_test)} |",
        f"| Average precision (chance = positive rate) | {ap:.3f} |",
        f"| Brier score (lower is better; always predicting the base rate = {brier_base:.3f}) |"
        f" {brier:.3f} |",
        f"| Precision among the {top_n} pull requests it ranks highest (top 20%) |"
        f" {_pct(top_precision)} |",
        "",
        "### Does it beat a trivial baseline?",
        (
            f"Yes, slightly: {meta['heldout_auc']:.3f} against {meta['heldout_size_only_auc']:.3f}"
            " for the size of the change alone."
            if beats
            else f"**No.** On the held-out pull requests it scores {meta['heldout_auc']:.3f}, the"
            f" size of the change alone scores {meta['heldout_size_only_auc']:.3f} and gradient"
            f" boosting {meta['heldout_gbm_auc']:.3f}. The difference ({gap:+.3f}) is far smaller"
            ' than the uncertainty, so what it knows beyond "bigger changes get more review" is'
            " not measurable with this data."
        ),
        "",
        "### Which numbers to trust",
        f"Cross-validation inside the training part reaches about {cv_mean:.2f} AUC, but its"
        " random folds mix pull requests from the same repository and the same period, which"
        " flatters the model. The held-out newest pull requests and the leave-one-repository-out"
        " table below are the honest figures.",
        "",
        "Cross-validated AUC on the training part (mean +/- std): "
        + ", ".join(f"C={c}: {m:.3f}+/-{s:.3f}" for c, (m, s) in cv.items())
        + f"; size only {size_cv[0]:.3f}; gradient boosting {gbm_cv[0]:.3f}.",
        "",
        "### Calibration (test part, lowest to highest predicted risk)",
        "| Mean predicted | Observed rate | Pull requests |",
        "| --- | --- | --- |",
        *[f"| {_pct(p)} | {_pct(o)} | {n} |" for p, o, n in calibration],
        *(
            [
                "",
                "The highest-risk group is over-confident: the model predicts about"
                f" {_pct(top_bin[0])} but {_pct(top_bin[1])} happened. Read high estimates as"
                ' "more likely than usual", not as a probability to rely on.',
            ]
            if overconfident and top_bin is not None
            else []
        ),
        "",
        "### Repositories it has never seen (leave-one-repository-out AUC)",
        "| Repository | AUC |",
        "| --- | --- |",
        *[f"| {r} | {a:.3f} |" for r, a in loo.items()],
        f"\nMean: {np.mean(list(loo.values())):.3f}." if loo else "",
        "",
        "## What drives the estimate (standardised coefficients, log-odds per standard deviation)",
        "| Feature | Coefficient |",
        "| --- | --- |",
        *[f"| `{n}` | {c:+.3f} |" for n, c in coefficients[:10]],
        "",
        "## How it is used",
        "- The review summary shows the estimate only when the lower end of the held-out AUC"
        " interval is above 0.5 (better than chance by a margin the data can support); the"
        " line states the held-out AUC so a reader can judge it.",
        "- It is worded as an estimate for pull requests that look like this, not as a judgement of"
        " this author or this code.",
        "",
        "## Limits",
        "- Trained on a small set of public repositories (mostly open-source projects); its"
        " behaviour on a private or differently run repository is not measured.",
        "- A model of size and shape mostly learns that big changes get more review. Treat it as"
        " a prompt to look more carefully, never as a verdict.",
        "- Retrain with `uv run lyvern ml collect ...` then `uv run lyvern ml train` when more"
        " data is available; the card is regenerated.",
        "",
        f"Trained {meta['trained_at']} with scikit-learn {meta['sklearn_version']}.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


__all__ = ["math", "train_and_report"]
