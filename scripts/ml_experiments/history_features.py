"""Experiment: do leak-free history features beat the current attention model on held-out PRs?"""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from lyvern.ml.train import load_dataset, temporal_split, bootstrap_auc, label_value
import csv

ROOT = Path(r"C:\Users\BHUVAN\dev\pr-intel\data\ml")
data = load_dataset(ROOT / "prs.csv", "inline_feedback")
rows = list(csv.DictReader(open(ROOT / "prs.csv", encoding="utf-8")))
rows = [r for r in rows if r.get("log_additions") not in (None, "")]
assert len(rows) == len(data.y)
authors = {}
for line in open(ROOT / "prs_raw.jsonl", encoding="utf-8"):
    r = json.loads(line)
    authors[(r["repo"], int(r["number"]))] = (r["pr"].get("author") or "").lower()

t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
LAG = timedelta(days=3)  # an earlier PR's outcome counts only if it was opened 3+ days before
n = len(rows)
created = [t(r["created_at"]) for r in rows]
repo = [r["repo"] for r in rows]
auth = [authors.get((r["repo"], int(r["number"])), "") for r in rows]
y = data.y
train, test = temporal_split(data)

# Global prior from training rows only, for smoothing.
g = y[train].mean()
K = 10
hist = np.zeros((n, 5))
for i in range(n):
    prev = [j for j in range(n) if repo[j] == repo[i] and created[j] <= created[i] - LAG]
    rp = sum(y[j] for j in prev)
    hist[i, 0] = (rp + K * g) / (len(prev) + K)  # repo prior rate (smoothed)
    ap = [j for j in prev if auth[j] == auth[i] and auth[i]]
    hist[i, 1] = np.log1p(len(ap))  # author's earlier PRs in the repo
    hist[i, 2] = (sum(y[j] for j in ap) + 3 * hist[i, 0]) / (len(ap) + 3)  # author prior rate
    recent = [j for j in prev if created[j] >= created[i] - timedelta(days=60)]
    hist[i, 3] = (sum(y[j] for j in recent) + K * g) / (len(recent) + K)  # recent repo rate
    hist[i, 4] = float(len(ap) == 0)  # new to this repo (in our sample)

X0 = data.x
X1 = np.hstack([X0, hist])


def lr(c=0.3):
    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=3000))


def gbm():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, l2_regularization=1.0, random_state=0)


def ev(name, model, X):
    model.fit(X[train], y[train])
    p = model.predict_proba(X[test])[:, 1]
    lo, hi = bootstrap_auc(y[test], p)
    print(f"{name:38s} AUC {roc_auc_score(y[test], p):.3f} [{lo:.3f},{hi:.3f}]  AP {average_precision_score(y[test], p):.3f}")
    return p


print("test rows", test.sum(), "positives", y[test].sum())
size = X0[:, [2]]
ev("size only (baseline)", lr(), size)
p0 = ev("current: 33 features, logreg", lr(), X0)
ev("history only (5)", lr(), hist)
p1 = ev("33 + history, logreg", lr(), X1)
ev("33 + history, gbm", gbm(), X1)
ev("size + history, logreg", lr(), np.hstack([size, hist]))

# Paired bootstrap: is (33+history) really better than current?
rng = np.random.default_rng(0)
yt = y[test]
d = []
for _ in range(2000):
    idx = rng.integers(0, len(yt), len(yt))
    if yt[idx].min() == yt[idx].max():
        continue
    d.append(roc_auc_score(yt[idx], p1[idx]) - roc_auc_score(yt[idx], p0[idx]))
d = np.array(d)
print(f"paired AUC gain {d.mean():+.3f}, 95% CI [{np.percentile(d,2.5):+.3f},{np.percentile(d,97.5):+.3f}], P(gain>0)={(d>0).mean():.2f}")
