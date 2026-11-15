# ROADMAP

Status: plan v0.1. Effort is in focused developer-days for one person and is an estimate, not a commitment. A phase is done only when its acceptance criteria are verified and logged in `SESSION_LOG.md`.

Phase 0 (this foundation): COMPLETE when the owner approves the documents. Phase 1 starts only after approval.

---
## M1. Engineering foundation (Phase 1)
- **Objective**: reproducible monorepo where api, worker, web, Postgres and Redis start with one command and CI is green.
- **Components**: uv workspace (Python), pnpm workspace (web), `apps/api` health endpoints, `apps/worker` hello task, `apps/web` shell, Docker Compose (pgvector Postgres, Redis), Alembic init, Ruff + mypy + pytest, ESLint + Prettier + Vitest, pre-commit, GitHub Actions, `.env.example`.
- **Modules**: `apps/*`, `infrastructure/docker`, `.github/workflows`, `scripts/`.
- **Dependencies**: Docker daemon running; Node 24, Python 3.12 (present).
- **Risks**: Docker on Windows file-sharing speed; port conflicts; Windows path quirks.
- **Tests**: API health test, worker task round trip through Redis, migration up/down on empty DB, web build.
- **Acceptance**: `docker compose up` brings healthy services; `/readyz` checks DB and Redis; CI runs lint, types, tests on a clean checkout and passes.
- **Effort**: 3-4 days.

## M2. GitHub App core (Phase 2a)
- **Objective**: secure ingestion of PR events and storage of review jobs.
- **Components**: signature verification, delivery dedup, event router, installation/repository sync, installation-token client with caching, GitHub API client with rate-limit and retry handling, review-run state machine, audit log, Celery job.
- **Modules**: `apps/api/webhooks`, `printel/github/`, `printel/db/`.
- **Dependencies**: M1; a test GitHub App registered by the owner (needs owner action); a public tunnel for local webhooks.
- **Risks**: webhook ordering and bursts; token expiry; rate limits; GitHub API pagination of files.
- **Tests**: signature valid/invalid/tampered, duplicate delivery, out-of-order events, token refresh, rate-limit backoff using recorded fixtures; one manual end-to-end on a throwaway repo.
- **Acceptance**: opening a PR on a test repo creates exactly one review run with the PR file list and patches stored; replaying the same delivery creates none; a forged request is rejected.
- **Effort**: 6-8 days.

## M3. Diff intelligence + publisher (Phase 2b/3a)
- **Objective**: correct diff parsing and safe comment publishing, proven with a trivial rule.
- **Components**: unified-diff parser (hunks, line maps, renames, binary, no-newline marker), generated/vendored/lockfile skip rules, large-PR strategy (priority ordering and truncation notices), line-validity checker, review publisher (`COMMENT` only), stale-SHA handling.
- **Modules**: `engine/diff_parser`, `printel/github/publisher.py`.
- **Dependencies**: M2.
- **Risks**: off-by-one line mapping; CRLF; huge diffs; rename+edit.
- **Tests**: property-based tests on generated diffs, golden fixtures from real PRs, round-trip of added-line positions against the GitHub API.
- **Acceptance**: a demo rule ("TODO added") produces inline comments on exactly the right lines of a real test PR; invalid locations are never posted; large PR produces an explicit truncation note.
- **Effort**: 5-6 days.

## M4. Code understanding (Phase 3b)
- **Objective**: structural facts for Python, JS, TS; Go afterwards.
- **Components**: `LanguageAdapter` protocol, Python adapter (ast + tree-sitter), JS/TS adapter (tree-sitter), symbol extraction, import graph, name-based call graph, changed-line -> symbol map, caller lookup across files, explicit limitation records, Go adapter.
- **Modules**: `engine/code_intelligence`.
- **Dependencies**: M3; tree-sitter Python bindings and grammars (install and version-pin; verify wheels on Windows and Linux).
- **Risks**: dynamic languages make call resolution approximate; TS path aliases; monorepo module resolution.
- **Tests**: fixture repos per language with known symbol/call tables; syntax-error files must degrade, not crash; limitation reporting tests.
- **Acceptance**: on fixture projects, extracted symbols and resolved cross-file callers match hand-written expectations; unresolved references are labelled unresolved.
- **Effort**: 8-10 days (Go +3).

## M5. Static analysis integration (Phase 3c)
- **Objective**: deterministic, evidence-backed findings.
- **Components**: Semgrep, Ruff, ESLint, secret scanner, dependency audit adapters; normalization to the finding model; evidence extraction from our own file reads; severity mapping table; sandboxed subprocess runner (timeouts, memory caps, no network, no repo-supplied configs trusted).
- **Modules**: `engine/static_analysis`.
- **Dependencies**: M3, M4 (for symbol mapping); analyzer licenses reviewed.
- **Risks**: analyzer noise; Semgrep registry rule license terms; ESLint needs a project config and plugins; Windows vs Linux behavior.
- **Tests**: vulnerable fixtures per category (SQLi, command injection, deserialization, hardcoded secret, path traversal, weak crypto); clean fixtures must produce zero findings; timeouts enforced.
- **Acceptance**: each listed vulnerability class detected on its fixture with correct file/line/evidence; zero findings on clean fixtures; analyzers killed on timeout.
- **Effort**: 7-9 days.

## M6. ML baselines and benchmark data (Phase 4a)
- **Objective**: measured baselines and a hand-verified benchmark.
- **Components**: dataset manifests and licenses, preprocessing, E1 classifier experiments, E2 embedding comparison, E3 rule-based risk model, evaluation reports, benchmark PR set with labels.
- **Modules**: `ml/*`, `engine/risk_engine`, `engine/semantic_search`.
- **Dependencies**: M5 (findings to classify); disk budget; license review of every dataset.
- **Risks**: weak or leaky labels; small benchmark; time cost of manual labeling; model size on disk.
- **Tests**: leakage tests (no repo/PR in two splits), metric computation tests against hand-computed cases, determinism with fixed seeds.
- **Acceptance**: reproducible `evaluate` command prints metrics for each candidate on a held-out split; ML_DESIGN.md updated with real numbers and limitations; no model ships without a model card.
- **Effort**: 10-14 days.

## M7. LLM review engine (Phase 5a)
- **Objective**: provider-neutral, schema-validated reasoning with budgets.
- **Components**: `LLMProvider` protocol + 2 providers, prompt builder with untrusted-data delimiting, token budgeter, redaction, schema validation + repair-or-discard, retries/timeouts, cost accounting, injection test corpus.
- **Modules**: `printel/llm/`, `engine/review_orchestrator/context.py`.
- **Dependencies**: M4, M5; owner-provided API key and cost ceiling.
- **Risks**: prompt injection, hallucinated lines, cost blow-ups, provider drift.
- **Tests**: mock provider tests, malformed-JSON handling, injection corpus must not change behavior, redaction tests, budget enforcement.
- **Acceptance**: every LLM finding validates against the schema, cites a real changed location, is labelled `llm_observation`, and a run never exceeds the configured cost cap.
- **Effort**: 7-9 days.

## M8. Orchestration + end-to-end review (Phase 5b)
- **Objective**: full pipeline on real PRs.
- **Components**: orchestrator steps, dedup, ranking, risk engine integration, summary generator, supersede logic, persistence, partial-failure handling.
- **Modules**: `engine/review_orchestrator`, `engine/risk_engine`, `apps/worker`.
- **Dependencies**: M2-M7.
- **Risks**: latency; flaky analyzers; comment spam.
- **Tests**: golden end-to-end fixtures with recorded GitHub API and mock LLM; chaos tests (analyzer crash, LLM timeout) -> `partial` runs.
- **Acceptance**: a real PR on a test repo gets one review with valid inline comments, a risk summary with factor explanation, and a persisted run; failure of any single step still yields a labelled partial review.
- **Effort**: 6-8 days.

## M9. Auth + dashboard foundation (Phase 6a)
- **Objective**: authenticated, tenant-isolated dashboard shell with real data and empty states.
- **Components**: GitHub OAuth, sessions, org/membership, generated API client, layout, overview, repositories, PR history, review detail, settings, design tokens (crimson on graphite), accessibility baseline.
- **Modules**: `apps/web`, `apps/api/routers`.
- **Dependencies**: M2, M8; design direction (final brand pending, use neutral wordmark placeholder).
- **Risks**: cross-site cookies between Vercel and API host; tenant leakage.
- **Tests**: cross-tenant access tests, Playwright e2e of login -> repo list -> review detail, axe accessibility checks.
- **Acceptance**: a user sees only their orgs' data; every page has a designed empty state; no hardcoded or fake numbers anywhere (grep test for fixture data in production build).
- **Effort**: 10-12 days.

## M10. Findings center, analytics, feedback (Phase 6b/J)
- **Objective**: search, filter, resolve/dismiss, recurring issues, export, quality analytics.
- **Components**: findings explorer, feedback capture (dashboard + GitHub reactions/resolution), analytics endpoints with sample sizes, charts (Recharts), SARIF/CSV/JSON export, ML evaluation and cost pages.
- **Dependencies**: M8, M9, M6 results.
- **Risks**: misleading metrics from tiny samples; feedback ambiguity.
- **Tests**: analytics unit tests vs. SQL fixtures, "insufficient data" states, export format validation (SARIF schema).
- **Acceptance**: metrics shown equal DB truth on fixtures; low-sample metrics are visibly flagged; exports validate.
- **Effort**: 8-10 days.

## M11. Quality and security hardening (Phase 7)
- **Objective**: confidence for real users.
- **Components**: full security test suite, performance tests on large PRs, benchmark comparison report vs. baselines, false-positive analysis, failure recovery drills, dependency scanning in CI.
- **Acceptance**: security checklist in SECURITY.md verified item by item; benchmark report published in docs with sample sizes and limitations; no unqualified superiority claims.
- **Effort**: 8-10 days.

## M12. Deployment (Phase 8)
- **Objective**: production deployment with monitoring.
- **Components**: production images, migrations job, worker deployment, secrets management, GitHub App production config, logging/monitoring/alerts, backup and restore test, runbook.
- **Dependencies**: hosting choice (Q4), domain, final brand name.
- **Acceptance**: deployed app reviews a real PR end to end; restore from backup verified; rollback procedure tested.
- **Effort**: 5-7 days.

**Rough total**: 85-110 focused developer-days. The thinnest useful slice (M1-M3 + M5 Semgrep/Ruff + simple orchestrator) is a demonstrable MVP at roughly 25-30 days.

## Suggested cut for a first demo
M1, M2, M3, M5 (Python only: Semgrep + Ruff + secrets), a minimal M8 pipeline, and a read-only slice of M9. This gets real evidence-backed comments on a real PR before the heavier ML and LLM work.
