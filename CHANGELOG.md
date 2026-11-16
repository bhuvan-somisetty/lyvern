# Changelog

All notable changes. Dates are in IST. This project is a work in progress; see `docs/BENCHMARK.md` for what has actually been measured.

## Unreleased (branch phase-1/foundation)
- GitHub App with signed webhooks, idempotent ingestion, background review job, inline comments, REQUEST_CHANGES, dismissal of its own stale review, and per-repository opt-in APPROVE (all verified in the owner's sandbox repository only).
- Reviewer mode CLI (`lyvern review`, read-only) and benchmark harness (`lyvern benchmark`).
- Analysis: Ruff (Python), tree-sitter rules for JavaScript and TypeScript, explainable risk score.
- Optional AI observations (Groq or Gemini): schema-validated, evidence-checked, never blocking.
- Dashboard: token-protected read-only API and overview / run-detail pages.
- 2026-11-16: conflict re-check when a pull request's target branch is pushed (needs the Push event subscription).
- 2026-11-16: findings are stored per run; owner verdicts (real / false alarm / not sure) and a measured precision endpoint with Wilson intervals; dashboard password login (signed cookie, login throttle, proxy guard).
- 2026-11-16: merge-conflict notice (one comment per head commit with rebase steps; branch names sanitised) and a rule that a pull request with merge conflicts is never approved.
- 2026-11-16: development App renamed to `lyvern-bot`; logo added.
- 2026-11-16: provider network errors now surface as clean errors; Gemini default model changed to `gemini-flash-lite-latest`.
- 2026-11-16: Go analyser (8 rules, tree-sitter) wired into the review pipeline; 18 Go cases added to the synthetic suite (79 cases).
- 2026-11-16: cross-file check for removed symbols that other files still reference; dashboard user accounts with roles (migration 0005), `lyvern user ...` admin CLI, verdicts record who gave them; advisory attention model (data collection, training, model card).
- 2026-11-16: dependency vulnerability check against OSV (pinned requirements.txt, package.json, go.mod), opt-in; `lyvern review --deps`.
- 2026-11-16: `docker compose up -d --build` now runs the dashboard (new `web` service and image) next to the API, worker, database and Redis; GitHub App settings are passed as environment variables and the private key is mounted read-only from the host.
