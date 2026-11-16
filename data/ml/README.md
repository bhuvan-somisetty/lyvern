# Training data for the attention model

`prs.csv` has one row per pull request, numbers only: repository, PR number, creation date, three
labels and 33 features (see `packages/lyvern/src/lyvern/ml/features.py`). No usernames, titles or
text.

**Provenance.** 1,200 closed pull requests (150 each) from 8 public repositories listed in
`repos.txt`, newest first, bot-authored ones skipped, collected on 2026-11-16 with read-only GitHub
API calls (`uv run lyvern ml collect --repos data/ml/repos.txt --per-repo 150`). The raw records
(`prs_raw.jsonl`, with usernames and PR text) are not committed; the command above rebuilds them,
and `uv run lyvern ml featurize` turns them into `prs.csv`.

**Labels.** `human_inline_comments` = top-level inline review comments by a person other than the
author. The model target `inline_feedback` is `human_inline_comments >= 1` (10.6% of rows).
`changes_requested` (2.4% of rows) and `human_reviewed` are kept for reference.

**Retrain.** `uv run lyvern ml train` splits each repository by time (oldest 70% train, newest 30%
test), writes `packages/lyvern/src/lyvern/ml/attention_model.json` and regenerates
`docs/ML_MODEL_CARD.md` with every figure. Result and limits: see the model card.
