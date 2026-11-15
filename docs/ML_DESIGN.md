# ML_DESIGN

Status: design v0.1. No dataset has been downloaded, no model trained, no metric measured. Every number in this project must come from `ml/evaluation` runs recorded here.

## 0. Principles
- Calling an LLM API is not machine learning and is not listed as such.
- Baselines first (rules, majority class, TF-IDF + linear model), then complexity only if it measurably wins.
- Splits: training/validation/test separated before any feature fitting; group splits by repository and, where possible, by time, so the same project, PR or near-duplicate code never appears on both sides (leakage control). Deduplicate near-identical examples before splitting.
- Report with confidence intervals or bootstrap ranges and the sample size. Fix random seeds; log package versions and dataset manifest hashes.
- Model cards for every shipped model: data, intended use, metrics, known failures.
- No synthetic labels presented as ground truth. Synthetic data (e.g. NIST Juliet) may be used for smoke tests only and is labelled as such.

## E1. Finding classification
Task: classify a finding's text (+ rule id + code snippet) into correctness, security, performance, maintainability, reliability, testing, documentation.
- Data: no labeled finding corpus exists yet. Sources to evaluate (licenses and label quality unverified, must be checked before use): the CodeReviewer review-comment dataset published with Microsoft's CodeBERT repo (cloned and present locally, data not yet fetched), public static-analyzer rule metadata (Semgrep/Ruff/ESLint rule categories and CWE mappings, giving weak labels), and our own manually labeled findings from the benchmark PRs.
- Models compared on the same split: majority baseline; rule-id lookup; TF-IDF + logistic regression; random forest or XGBoost on TF-IDF/SVD plus metadata; small embedding + logistic regression.
- Metrics: accuracy, per-class precision/recall/F1, macro-F1, confusion matrix, calibration (reliability curve, Brier score).
- Expected difficulty: class imbalance and weak labels. Weak-label evaluation will be reported as weak-label performance, not true accuracy; a hand-labeled test set (target: a few hundred findings) is required before any production claim.

## E2. Semantic code similarity
Task: given a changed function or a finding, retrieve similar historical code or findings.
- Candidates: sentence-transformers general model (small, fast), CodeBERT (`microsoft/codebert-base`), UniXcoder, and GraphCodeBERT (all in Microsoft's code-pretraining repo, which is cloned locally). Hypothesis to test, not a fact: raw CodeBERT mean-pooled vectors are weak for retrieval compared with models trained for embeddings or code search; the benchmark decides.
- Benchmark: a retrieval set built from labeled pairs (same bug pattern or clone vs. unrelated) from licensed public data plus hand-verified pairs. Metrics: Precision@K, Recall@K, MRR, nDCG, plus latency and memory on CPU. Compare against BM25/TF-IDF as a baseline.
- Storage: pgvector (HNSW, cosine). Index parameters tuned on the benchmark.
- Resource constraint: about 14 GB free disk on the dev machine; use CPU-only PyTorch and cache models in a known folder; record model download sizes.

## E3. PR risk prediction
- v1 is an explainable rule/statistical baseline (Module H), not a trained model. Features: files changed, lines added/removed, number of changed symbols, number of cross-file callers of changed symbols, dependency manifest changes, security-sensitive paths (auth, crypto, CI config, migrations), tests changed vs. source changed, complexity delta (cyclomatic from AST), author/file churn history when available. The score is a transparent weighted sum with per-factor contributions displayed.
- Supervised model gate: only attempted if there is a defensible label such as "PR was later reverted or needed a fix-forward within N days" mined from real repositories, with the noise of that proxy documented (SZZ-style approaches have known false labels). Until then, no claim of "predicted defect probability".
- Evaluation if gated in: time-based split, ROC-AUC and PR-AUC (class imbalance), calibration, comparison against the rule baseline and against a size-only baseline (lines changed alone is a strong baseline in the literature).

## E4. Evaluation infrastructure
- `ml/evaluation/` holds scripts that read a dataset manifest and produce a metrics JSON and a Markdown report; results are inserted into `ml_evaluations` and shown in the dashboard "ML evaluation" page, empty until real runs exist.
- Review-quality benchmark (separate from ML): a set of real, licensed public PRs with manually verified expected findings. Records origin URL, license, labeling method, labeler, date and known limitations. Systems compared fairly under identical inputs: Semgrep-only, Ruff/ESLint-only, an LLM-only baseline, our pipeline. Metrics: precision, recall, F1 of findings against ground truth, false-positive rate per PR, comment usefulness from reviewer rating, cost per PR.
- Feedback learning: dashboard and GitHub reactions are logged as signals, not labels. A "dismiss" may mean "wrong", "not now" or "already known". A label is created only through a documented adjudication step.

## Reproducibility
`ml/` uses a pinned environment, `make` or script entrypoints (`train`, `evaluate`), seeds in config, and dataset manifests with source URL, license, SHA-256, and split assignment file committed (data itself not committed).

## Limitations to state in the product
Language coverage of parsers, weak labels, small benchmark size, LLM variability across versions, and that scores are triage aids, not guarantees.
