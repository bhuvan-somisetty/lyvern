"""Attention model: features, runtime, data collection, training protocol and pipeline use."""

import csv
import json
import math
from pathlib import Path
from typing import Any

import pytest

from lyvern.engine.contracts import ReviewEvent
from lyvern.github.client import GitHubError, GitHubRateLimited
from lyvern.github.models import (
    ChangedFileInfo,
    PullRequestInfo,
    ReviewCommentInfo,
    ReviewInfo,
)
from lyvern.github.refs import PullRequestRef
from lyvern.ml.dataset import (
    FIELDS,
    collect_repo,
    featurize,
    human_inline_comment_count,
    human_review_labels,
    is_bot,
    load_done,
    load_raw,
)
from lyvern.ml.features import FEATURE_NAMES, extract_features
from lyvern.ml.model import (
    DEFAULT_MODEL_PATH,
    AttentionModel,
    ModelFormatError,
    load_model,
    parse_model,
    render_attention,
)
from lyvern.review_pipeline import review_pull_request


def pr(**over: Any) -> PullRequestInfo:
    base: dict[str, Any] = {
        "owner": "o", "repo": "r", "number": 1, "title": "Fix crash on empty input",
        "body": "- [x] tests\n", "author": "alice", "state": "closed", "draft": False,
        "html_url": "u", "base_ref": "main", "base_sha": "b" * 40, "head_ref": "x",
        "head_sha": "a" * 40, "head_repo_full_name": "o/r", "changed_files": 3,
        "additions": 40, "deletions": 10, "author_association": "CONTRIBUTOR",
        "created_at": "2026-01-01T00:00:00Z", "merged": True,
    }  # fmt: skip
    base.update(over)
    return PullRequestInfo(**base)


def f(name: str, status: str = "modified", add: int = 10, dele: int = 0) -> ChangedFileInfo:
    return ChangedFileInfo(filename=name, status=status, additions=add, deletions=dele)


FILES = [
    f("src/app/main.py", add=30, dele=5),
    f("tests/test_main.py", "added", 10),
    f("README.md", add=2),
    f(".github/workflows/ci.yml", add=1),
    f("requirements.txt", add=1),
]


# --------------------------------------------------------------------------- features


def test_features_are_complete_finite_and_deterministic() -> None:
    a = extract_features(pr(), FILES)
    assert tuple(a) == FEATURE_NAMES and a == extract_features(pr(), FILES)
    assert all(math.isfinite(v) for v in a.values())


def test_feature_values_follow_the_definitions() -> None:
    x = extract_features(pr(), FILES)
    assert x["touches_tests"] == 1.0 and x["test_files_share"] == pytest.approx(1 / 5)
    assert x["docs_files_share"] == pytest.approx(1 / 5) and x["docs_only"] == 0.0
    assert x["ci_config_files"] == 1.0 and x["dependency_files"] == 1.0
    assert x["new_files_share"] == pytest.approx(1 / 5) and x["py_share"] == pytest.approx(2 / 5)
    assert x["title_fix"] == 1.0 and x["body_has_checklist"] == 1.0
    assert x["assoc_contributor"] == 1.0 and x["assoc_member"] == 0.0 and x["is_draft"] == 0.0
    assert x["log_total_churn"] == pytest.approx(math.log1p(49))
    assert x["n_top_dirs"] == 4.0  # src, tests, README.md ("."), .github, requirements ("." shared)


def test_edge_cases_do_not_crash_or_divide_by_zero() -> None:
    empty = extract_features(pr(title="", body="", changed_files=0, additions=0, deletions=0), [])
    assert all(math.isfinite(v) for v in empty.values()) and empty["add_share"] == 0.5
    docs = extract_features(pr(), [f("docs/a.md"), f("b.rst")])
    assert docs["docs_only"] == 1.0
    first = extract_features(pr(author_association="FIRST_TIME_CONTRIBUTOR"), FILES)
    owner = extract_features(pr(author_association="OWNER", draft=True, title="WIP: thing"), FILES)
    assert first["assoc_first_time"] == 1.0 and owner["assoc_member"] == 1.0
    assert owner["is_draft"] == 1.0 and owner["title_wip"] == 1.0


def test_features_never_read_the_outcome() -> None:
    import inspect

    from lyvern.ml import features

    source = inspect.getsource(features)
    for forbidden in ("pr.merged", "pr.state", "list_reviews", "review_comments", "human_"):
        assert forbidden not in source


# ----------------------------------------------------------------------------- runtime


def tiny_model(auc_low: float = 0.6, **meta: Any) -> AttentionModel:
    names = list(FEATURE_NAMES)
    coef = [0.0] * len(names)
    coef[names.index("log_total_churn")] = 1.0
    coef[names.index("touches_tests")] = -0.5
    payload = {
        "feature_names": names, "mean": [0.0] * len(names), "scale": [1.0] * len(names),
        "coef": coef, "intercept": -2.0,
        "meta": {"heldout_auc": 0.7, "heldout_auc_ci_low": auc_low, "base_rate": 0.1,
                 "n_train_rows": 800, **meta},
    }  # fmt: skip
    return parse_model(payload)


def test_prediction_is_a_monotonic_probability_and_matches_the_formula() -> None:
    model = tiny_model()
    small = model.predict({"log_total_churn": 1.0})
    big = model.predict({"log_total_churn": 6.0})
    assert 0 < small < big < 1
    assert big == pytest.approx(1 / (1 + math.exp(-(1.0 * 6.0 - 2.0))))
    assert model.predict({"log_total_churn": 800.0}) == pytest.approx(1.0)  # no overflow
    assert model.predict({"log_total_churn": -800.0}) == pytest.approx(0.0)
    assert model.logit({}) == -2.0  # a missing feature falls back to the training mean


def test_estimate_lists_the_biggest_factors_first() -> None:
    est = tiny_model().estimate({"log_total_churn": 5.0, "touches_tests": 1.0})
    assert est.factors[0][0] == "log_total_churn" and est.factors[0][1] == pytest.approx(5.0)
    assert est.factors[1] == ("touches_tests", pytest.approx(-0.5))
    assert est.trained_on == 800 and est.heldout_auc == 0.7


def test_the_estimate_is_shown_only_when_the_interval_excludes_chance() -> None:
    assert tiny_model(auc_low=0.6).displayable
    assert not tiny_model(auc_low=0.5).displayable
    assert not tiny_model(auc_low=0.45).displayable
    assert not parse_model({**_payload(), "meta": {}}).displayable


def _payload() -> dict[str, Any]:
    return {"feature_names": ["a"], "mean": [0.0], "scale": [1.0], "coef": [1.0], "intercept": 0.0}


def test_bad_model_files_are_rejected() -> None:
    for broken in (
        {**_payload(), "mean": [0.0, 1.0]},
        {**_payload(), "feature_names": []},
        {**_payload(), "coef": [float("inf")]},
        {k: v for k, v in _payload().items() if k != "intercept"},
        {**_payload(), "coef": ["x"]},
    ):
        with pytest.raises(ModelFormatError):
            parse_model(broken)


def test_load_model_handles_missing_and_reads_a_file(tmp_path: Path) -> None:
    assert load_model(tmp_path / "none.json") is None
    path = tmp_path / "m.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    assert load_model(path) is not None


def test_the_packaged_model_matches_the_feature_definitions() -> None:
    model = load_model()
    if model is None:
        pytest.skip("no packaged model yet")
    assert model.feature_names == FEATURE_NAMES  # retrain after changing the features
    assert DEFAULT_MODEL_PATH.exists() and model.meta["target"] == "inline_feedback"


def test_the_summary_line_is_plain_text_and_honest() -> None:
    est = tiny_model().estimate({"log_total_churn": 5.0, "touches_tests": 1.0})
    text = render_attention(est)
    assert "statistical estimate, advisory" in text and "not a finding" in text
    assert "size of the change (raises)" in text and "tests included (lowers)" in text
    assert "800 public pull requests" in text and "held-out AUC 0.70" in text
    assert all(ord(c) < 0x2190 for c in text)  # no emoji


# ------------------------------------------------------------------- pipeline integration


class Source:
    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        return pr(changed_files=1, additions=2, deletions=0)

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        patch = "@@ -0,0 +1,2 @@\n+def add(a, b):\n+    return a + b\n"
        return [
            ChangedFileInfo(filename="ok.py", status="added", additions=2, deletions=0, patch=patch)
        ]

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return "def add(a, b):\n    return a + b\n"


REF = PullRequestRef("o", "r", 1)


def test_the_estimate_appears_in_the_summary_only_when_a_displayable_model_is_given() -> None:
    shown = review_pull_request(Source(), REF, attention=tiny_model(auc_low=0.6))
    assert shown.attention is not None and "Review attention" in shown.summary
    assert shown.decision.event == ReviewEvent.COMMENT  # never changes the verdict
    for model in (None, tiny_model(auc_low=0.4)):
        draft = review_pull_request(Source(), REF, attention=model)
        assert draft.attention is None and "Review attention" not in draft.summary


def test_the_estimate_never_changes_findings_or_the_decision() -> None:
    from lyvern.engine.policy import ReviewPolicy

    policy = ReviewPolicy(allow_approve=True)
    with_model = review_pull_request(Source(), REF, policy, attention=tiny_model())
    without = review_pull_request(Source(), REF, policy)
    assert with_model.decision.event == without.decision.event == ReviewEvent.APPROVE
    assert with_model.findings == without.findings and with_model.risk == without.risk


# ----------------------------------------------------------------------------- dataset


def review(state: str, author: str = "bob", kind: str = "User") -> ReviewInfo:
    return ReviewInfo(state=state, author=author, author_type=kind)


def comment(author: str = "bob", kind: str = "User", reply: int | None = None) -> ReviewCommentInfo:
    return ReviewCommentInfo(
        path="a.py", body="x", author=author, author_type=kind, in_reply_to_id=reply
    )


def test_labels_ignore_the_author_bots_and_replies() -> None:
    reviews = [review("COMMENTED", "alice"), review("CHANGES_REQUESTED", "bot", "Bot")]
    assert human_review_labels("alice", reviews) == {
        "changes_requested": 0, "human_reviewed": 0, "human_inline_comments": 0,
    }  # fmt: skip
    reviews.append(review("CHANGES_REQUESTED", "bob"))
    comments = [comment("bob"), comment("bob", reply=5), comment("alice"), comment("ci", "Bot")]
    labels = human_review_labels("alice", reviews, comments)
    assert labels == {"changes_requested": 1, "human_reviewed": 1, "human_inline_comments": 1}
    assert human_inline_comment_count("alice", [comment("bob"), comment("carol")]) == 2
    assert is_bot("dependabot[bot]") and is_bot("Renovate") and not is_bot("alice")


class FakeClient:
    def __init__(self, count: int = 6, limited_at: int | None = None) -> None:
        self.count, self.limited_at = count, limited_at
        self.calls: list[str] = []

    def list_pull_requests(self, owner: str, repo: str, **kw: Any) -> list[PullRequestInfo]:
        authors = ["alice", "dependabot[bot]", "bob"]
        return [pr(number=n, author=authors[n % 3]) for n in range(1, self.count + 1)]

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        self.calls.append(f"pr{ref.number}")
        if ref.number == self.limited_at:
            raise GitHubRateLimited(None)
        if ref.number == 6:
            raise GitHubError(500, "boom")
        return pr(number=ref.number, author="alice" if ref.number % 3 == 1 else "bob",
                  changed_files=0 if ref.number == 5 else 2)  # fmt: skip

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        return FILES

    def list_reviews(self, ref: PullRequestRef) -> list[ReviewInfo]:
        return [review("CHANGES_REQUESTED", "carol")] if ref.number % 2 else []

    def list_review_comments(self, ref: PullRequestRef) -> list[ReviewCommentInfo]:
        return [comment("carol")]


def rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_collection_skips_bots_empty_and_failing_pull_requests_and_resumes(tmp_path: Path) -> None:
    out, logs = tmp_path / "raw.jsonl", []
    done: set[tuple[str, int]] = set()
    added, limited = collect_repo(
        FakeClient(), "o/r", out, target=10, done=done, log=logs.append, workers=2
    )
    records = list(load_raw(out))
    assert not limited and added == len(records)
    # 1 and 4 are bot-authored, 5 has no files, 6 fails: only 2 and 3 are kept
    assert {r["number"] for r in records} == {2, 3}
    assert load_done(out) == {("o/r", 2), ("o/r", 3)}
    first = records[0]
    assert first["labels"]["human_inline_comments"] == 1 and len(first["files"]) == len(FILES)
    assert all("patch" not in f for f in first["files"])  # file names and counts only, no code
    again, _ = collect_repo(
        FakeClient(), "o/r", out, target=10, done=load_done(out), log=logs.append
    )
    assert again == 0 and len(list(load_raw(out))) == 2  # nothing is fetched or written twice


def test_collection_stops_cleanly_at_the_rate_limit(tmp_path: Path) -> None:
    out = tmp_path / "raw.jsonl"
    added, limited = collect_repo(
        FakeClient(limited_at=3), "o/r", out, target=10, done=set(), log=lambda _m: None, workers=1
    )
    assert limited and added == 1 and {r["number"] for r in load_raw(out)} == {2}


def test_featurize_rebuilds_the_csv_from_raw_records_without_the_network(tmp_path: Path) -> None:
    raw, csv_path = tmp_path / "raw.jsonl", tmp_path / "prs.csv"
    collect_repo(FakeClient(), "o/r", raw, target=10, done=set(), log=lambda _m: None, workers=1)
    assert featurize(raw, csv_path) == 2
    rows = rows_of(csv_path)
    assert list(rows[0]) == list(FIELDS) and {r["number"] for r in rows} == {"2", "3"}
    expected = extract_features(pr(number=2, author="bob"), FILES)
    assert float(rows[0]["log_total_churn"]) == pytest.approx(expected["log_total_churn"], abs=1e-5)
    assert (
        rows[0]["human_inline_comments"] == "1" and rows[0]["created_at"] == "2026-01-01T00:00:00Z"
    )
    # a change to the features only needs this step again, not new API calls
    assert featurize(raw, csv_path) == 2


# ------------------------------------------------------------------------------ training

pytest.importorskip("sklearn")

import numpy as np  # noqa: E402

from lyvern.ml import train  # noqa: E402


def write_synthetic(path: Path, n_per_repo: int = 150, signal: float = 1.5, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for repo in ("a/one", "b/two", "c/three"):
            for i in range(n_per_repo):
                size = float(rng.normal(4, 1.5))
                row: dict[str, Any] = dict.fromkeys(FEATURE_NAMES, 0.0)
                row["log_total_churn"] = size
                row["touches_tests"] = float(rng.random() < 0.5)
                p = 1 / (1 + math.exp(-(signal * (size - 4) - 1.0)))
                label = int(rng.random() < p)
                row.update(
                    repo=repo, number=i, created_at=f"2026-01-{1 + i // 10:02d}T{i % 10:02d}:00:00Z",
                    merged=1, author="x", changes_requested=0, human_reviewed=label,
                    human_inline_comments=label * 2,
                )  # fmt: skip
                writer.writerow(row)


def test_temporal_split_puts_the_oldest_of_each_repository_in_training() -> None:
    data = train.Dataset(
        repos=["a"] * 10 + ["b"] * 10,
        created=[f"2026-01-{i + 1:02d}" for i in range(10)] * 2,
        x=np.zeros((20, 1)),
        y=np.array([0, 1] * 10),
    )
    tr, te = train.temporal_split(data, 0.7)
    assert tr.sum() == 14 and te.sum() == 6 and not (tr & te).any()
    for repo in ("a", "b"):
        mask = np.array(data.repos) == repo
        train_dates = [d for d, m in zip(data.created, tr & mask, strict=True) if m]
        test_dates = [d for d, m in zip(data.created, te & mask, strict=True) if m]
        assert max(train_dates) < min(test_dates)  # the model never trains on the future


def test_derived_targets_and_data_checks(tmp_path: Path) -> None:
    assert train.label_value({"human_inline_comments": "0"}, "inline_feedback") == 0
    assert train.label_value({"human_inline_comments": "1"}, "inline_feedback") == 1
    assert train.label_value({"human_inline_comments": "2"}, "heavy_feedback") == 0
    assert train.label_value({"human_inline_comments": "3"}, "heavy_feedback") == 1
    assert train.label_value({"changes_requested": "1"}, "changes_requested") == 1
    small = tmp_path / "small.csv"
    write_synthetic(small, n_per_repo=10)
    with pytest.raises(ValueError, match="at least"):
        train.load_dataset(small, "inline_feedback")
    one_class = tmp_path / "one.csv"
    write_synthetic(one_class, signal=0.0)
    rows = rows_of(one_class)
    with one_class.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            r["human_inline_comments"] = "0"
            writer.writerow(r)
    with pytest.raises(ValueError, match="one class"):
        train.load_dataset(one_class, "inline_feedback")


def test_training_finds_a_real_signal_and_exports_a_model_that_reproduces_sklearn(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "prs.csv"
    write_synthetic(data_path)
    model_path, card_path = tmp_path / "model.json", tmp_path / "card.md"
    summary = train.train_and_report(data_path, "inline_feedback", model_path, card_path)
    assert "held-out AUC" in summary

    model = load_model(model_path)
    assert model is not None and model.feature_names == FEATURE_NAMES
    assert model.meta["heldout_auc"] > 0.7 and model.displayable
    assert (
        model.meta["heldout_auc_ci_low"]
        < model.meta["heldout_auc"]
        < model.meta["heldout_auc_ci_high"]
    )
    assert model.meta["n_eval_train"] + model.meta["n_eval_test"] == 450
    assert model.meta["repos"] == ["a/one", "b/two", "c/three"]

    # the pure-Python runtime must reproduce what the trained sklearn model predicts
    data = train.load_dataset(data_path, "inline_feedback")
    reference = train._logreg(model.meta["best_C"])
    reference.fit(data.x, data.y)
    expected = reference.predict_proba(data.x[:40])[:, 1]
    got = [
        model.predict(dict(zip(FEATURE_NAMES, row.tolist(), strict=True))) for row in data.x[:40]
    ]
    assert np.allclose(expected, got, atol=1e-9)
    # the size feature carries the signal, so its coefficient must be the largest
    assert max(zip(model.coef, FEATURE_NAMES, strict=True))[1] == "log_total_churn"

    card = card_path.read_text(encoding="utf-8")
    for needle in (
        "Model card",
        "evaluated once",
        "leave-one-repository-out",
        "Limits",
        "advisory",
    ):
        assert needle in card


def test_without_any_signal_the_model_is_not_shown(tmp_path: Path) -> None:
    data_path = tmp_path / "noise.csv"
    write_synthetic(data_path, signal=0.0, seed=3)
    train.train_and_report(data_path, "inline_feedback", tmp_path / "m.json", tmp_path / "c.md")
    model = load_model(tmp_path / "m.json")
    assert model is not None
    assert model.meta["heldout_auc_ci_low"] < 0.65  # no real signal: nothing to claim
