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
- 2026-11-17: the public demo and its sample data were removed at the owner's request (no fake data); dashboard restyled with the owner's saved palette and fonts; Lyvern logo as the browser-tab icon; `dangerouslySetInnerHTML` rule made opt-in after 0 of about 45 labelled cases were real (it also now recognises constants, sanitiser calls and escaped JSON-LD when enabled).
- 2026-11-17: (earlier today, now superseded) public demo dashboard on Vercel (sample data), redesigned interface; the empty-catch rule is now opt-in (`LYVERN_STRICT_STYLE_RULES`, `--strict-style`) after it was right in 8 of 56 labelled cases; minified and bundled files are treated as generated; exact line numbers for CRLF files.
- 2026-11-18: attention model retrained on 6,400 real public pull requests from 16 repositories: held-out AUC 0.75 (was 0.70), now clearly above the size-only baseline; card reports a paired bootstrap interval for that gain and flags repositories where it is near chance.
- 2026-11-16: attention model trained on 1,200 real public pull requests; `docs/ML_MODEL_CARD.md`; `data/ml/prs.csv`.
- 2026-11-16: cross-file check for removed symbols that other files still reference; dashboard user accounts with roles (migration 0005), `lyvern user ...` admin CLI, verdicts record who gave them; advisory attention model (data collection, training, model card).
- 2026-11-16: dependency vulnerability check against OSV (pinned requirements.txt, package.json, go.mod), opt-in; `lyvern review --deps`.
- 2026-11-16: `docker compose up -d --build` now runs the dashboard (new `web` service and image) next to the API, worker, database and Redis; GitHub App settings are passed as environment variables and the private key is mounted read-only from the host.
- Read-only snapshot mode for the dashboard (`LYVERN_SNAPSHOT=1`): serves an anonymised export of the real database (`scripts/export_dashboard_snapshot.py`, `apps/web/src/data/snapshot.json`) with repositories, files, commit ids and pull request links hidden. No login, no writes, no invented data. Used for the public Vercel site.
- README rewritten (live link, how it works, what the bot and dashboard do, measured limits).
- README: added sandbox PR walkthrough (repo is private; noted).
- Actions mode: `lyvern action` and `.github/workflows/lyvern-review.yml` run reviews on a free GitHub-hosted runner (no server). Rebuilds the bot's earlier reviews from GitHub so stale reviews are still dismissed. See `docs/ACTIONS_MODE.md`.
- MIT `LICENSE` added.
- Accuracy: first evaluation on six unseen repositories (precision 9/54 before fixes). Fixed re-export unused imports, attribute-read statements, justified `@ts-ignore`, benchmark and example code, and two noisy style rules. See `docs/BENCHMARK.md` section 7.
- Public site: new landing page for the snapshot mode (`/`), dashboard moved to `/dashboard`; real findings, real totals, calm motion, saved palette and fonts.
