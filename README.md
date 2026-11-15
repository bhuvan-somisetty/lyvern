# pr-intel (temporary project name)

Pull request intelligence for engineering teams: a GitHub App and dashboard that reviews pull requests using structural code analysis, established static-analysis tools, evaluated ML components and an LLM, and publishes evidence-backed feedback. It assists reviewers; it never merges, approves or pushes code.

The product name is not final. Repository, folder and Python package (`printel`) use a temporary identifier.

Status: Phase 1 (engineering foundation). Nothing reviews pull requests yet. See `docs/ROADMAP.md`.

## Layout
- `apps/api` FastAPI service, `apps/worker` Celery worker, `apps/web` Next.js dashboard
- `packages/printel` shared Python core (settings, logging, database, queue)
- `docs/` specification, architecture, security, roadmap, decisions, session log

## Run locally
Requirements: Docker, Python 3.12, `uv`, Node 24, `pnpm`.

```bash
cp .env.example .env
docker compose up -d --build       # db (host 5433), redis (host 6380), migrate, api (8000), worker
curl http://localhost:8000/readyz  # {"status":"ready", ...}
```

Host ports 5433 and 6380 avoid clashes with a local Postgres or Redis; override with `PRINTEL_DB_PORT` and `PRINTEL_REDIS_PORT`.

## Develop
```bash
uv sync --all-packages
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run alembic upgrade head
uv run pytest tests            # integration tests need `docker compose up -d`
cd apps/web && pnpm install && pnpm dev
```

## Documentation
Start with `PROJECT_RULES.md` and `docs/SESSION_LOG.md`.
