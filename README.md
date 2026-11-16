<p align="center"><img src="docs/assets/lyvern-bot-logo.png" alt="Lyvern bot logo" width="120"></p>

# Lyvern

Pull request intelligence for engineering teams: a GitHub App and dashboard that reviews pull requests using structural code analysis, established static-analysis tools, evaluated ML components and an LLM, and publishes evidence-backed feedback. It assists reviewers; it never merges, approves or pushes code.

Repository, folder and Python package are named `lyvern`. Trademark and domain checks for the name are still open.

Status: Phase 1 (engineering foundation). Nothing reviews pull requests yet. See `docs/ROADMAP.md`.

## Layout
- `apps/api` FastAPI service, `apps/worker` Celery worker, `apps/web` Next.js dashboard
- `packages/lyvern` shared Python core (settings, logging, database, queue)
- `docs/` specification, architecture, security, roadmap, decisions, session log

## Run locally
Requirements: Docker, Python 3.12, `uv`, Node 24, `pnpm`.

```bash
cp .env.example .env
docker compose up -d --build       # db (host 5433), redis (host 6380), migrate, api (8000), worker
curl http://localhost:8000/readyz  # {"status":"ready", ...}
```

Host ports 5433 and 6380 avoid clashes with a local Postgres or Redis; override with `LYVERN_DB_PORT` and `LYVERN_REDIS_PORT`.

## Develop
```bash
uv sync --all-packages
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run alembic upgrade head
uv run pytest tests            # integration tests need `docker compose up -d`
cd apps/web && pnpm install && pnpm dev
```

## Status (2026-11-16)
Built and verified: repository, CI (green on GitHub), Docker stack, API health endpoints, worker, migrations, dashboard shell, and the review engine core (finding model, diff parser verified against real `git diff`, dedup and ranking, comment placement, review decision engine, review rendering) with 75 unit tests.
Also built and verified: GitHub App connection (signed webhooks, review job, inline comments, request-changes, dismissal of its own stale review), run in the owner's sandbox repository only; read-only reviewer mode (`lyvern review <PR>`); Python (Ruff), JS/TS and Go (tree-sitter) analysis; known-vulnerability check for pinned dependencies (OSV, opt-in); merge-conflict notices; approval only with zero findings and no conflicts (per-repository opt-in); explainable risk score; optional AI layer; benchmark harness; dashboard with password login, findings with owner verdicts and measured precision. Also built: a cross-file check for removed symbols that are still used, dashboard accounts with roles, and an advisory attention model trained on public pull-request history (see `docs/ML_MODEL_CARD.md`). Not built: a full call graph and type-aware analysis, single sign-on, Semgrep and ESLint integration. Measured results and their limits are in `docs/BENCHMARK.md`; no accuracy claim beyond those exists.

## Where is the code
- `packages/lyvern/src/lyvern/engine/` review logic (contracts, diff, dedup, placement, decision, policy, render)
- `packages/lyvern/src/lyvern/` shared core (config, logging, database, Celery app)
- `apps/api` FastAPI service, `apps/worker` Celery worker, `apps/web` Next.js dashboard
- `tests/` unit and integration tests; `.github/workflows/ci.yml` CI

## Documentation
Start with `docs/PROJECT_HANDBOOK.md` (everything, A to Z), then `docs/PRD.md` (product requirements) and `docs/TRD.md` (technical requirements). Also: `PROJECT_RULES.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/API_SPECIFICATION.md`, `docs/ML_DESIGN.md`, `docs/SECURITY.md`, `docs/ROADMAP.md`, `docs/ENGINEERING_DECISIONS.md`, `docs/REFERENCE_RESEARCH.md`, `docs/SESSION_LOG.md`.
