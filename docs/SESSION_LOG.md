# SESSION_LOG

Append-only. Never edit or delete past entries; correct with a new line under the old one. Timestamps are real system-clock readings in IST (+05:30). No secrets in this file.

## Current status (update at every milestone)
- Last updated: 2026-11-16 ~04:15 IST (clock readings), Session 2.
- Phase 1 / M1 (engineering foundation): implemented; verification in progress (see Session 2 entries). Repo: C:\Users\BHUVAN\dev\pr-intel (outside OneDrive), branch `phase-1/foundation`, 4 commits in total (1 on `develop`, 3 on the branch), no remote.
- Verified locally: ruff, ruff format, mypy --strict, 15 Python tests, Alembic up/down/up, compose stack healthy, real worker round trip, web eslint/tsc/vitest/build, Python steps on a clean clone.
- NOT verified: GitHub Actions run (no remote), web steps on a clean clone (running), JSON access logs, product name still not chosen.
- Next planned action: finish M1 acceptance review; owner picks product name (search Vigyl, Skopyr, Oculyx, Auspyr and top five first); then M2 (GitHub App core), which needs the owner to register a dev GitHub App.

---

## Session 1 — 2026-11-15

### Time
Start 17:05 IST. Entries observed at 17:05, 17:08 and 17:11 IST (clock readings).

### Objective
Phase 0: inspect workspace, understand the directive, research references, write the foundation documents, run a naming exercise, produce a milestone plan, report, and stop for approval.

### Work completed
- Confirmed identity with the owner via a selection prompt: Bhuvan Somisetty. (The account's login email differs from both known identities; the owner's explicit answer was used.)
- Workspace inspection: directory was empty (no files), not a git repository.
- Tool inventory: Python 3.12.10, Node 24.14.0, npm 11.9.0, pnpm present, git 2.54.0, Docker 29.6.2 (daemon not yet tested), Go present, gh 2.92.0, Ruff present, Semgrep 1.161.0 present (installed under a Python 3.13 Scripts folder). Not found: psql, redis-server. Disk: about 14.2 GB free on C:.
- Reference research: shallow-cloned pr-agent, CodeBERT, tree-sitter into the session scratch folder (outside the project); read pr-agent layout, patch processing, deterministic risk, structural reach, token budgeting, webhook code, prompts; read CodeBERT and tree-sitter READMEs; ran Semgrep with a local rule to record real JSON output; web searches for GitHub App best practices and Qodo docs (search summaries only).
- Brand naming: 20 names generated; 10 searched (4 conflicts found and rejected); top five chosen from searched, conflict-free names.
- Wrote the 13 foundation documents (list below).

### Files changed
Created (project folder `AI PR Review Bot`):
- PROJECT_RULES.md
- docs/PRODUCT_SPEC.md, ARCHITECTURE.md, DATABASE_SCHEMA.md, API_SPECIFICATION.md, ML_DESIGN.md, SECURITY.md, ROADMAP.md, ENGINEERING_DECISIONS.md, REFERENCE_RESEARCH.md, BRAND_NAME_SHORTLIST.md, SESSION_LOG.md, CHANGELOG.md
Modified: none. Deleted: none.
Outside the project: scratch clones in the session scratchpad; Claude Code project memory log `project-session-log.md` (mirror of this log).
Not created yet (Phase 1): README.md, .gitignore, .env.example, any code or folders from the layout.

### Technical decisions
ED-001 to ED-013 recorded as Proposed in ENGINEERING_DECISIONS.md. Main ones: modular monolith + worker; Celery/Redis with DB as source of truth; tree-sitter + `ast`; reuse analyzers; COMMENT-only reviews; four finding origins; rule-based risk v1; pgvector; generated TS client; layout refinements.

### Commands and tests
- Directory listing and tool probing (PowerShell): succeeded; git reported "not a git repository", as expected.
- `git clone --depth 1` of pr-agent, CodeBERT, tree-sitter: succeeded.
- `semgrep scan --config r.yml --json --metrics=off` on a scratch file: succeeded, produced one finding (rule matched `subprocess.call(..., shell=True)`); output showed `lines`/`fingerprint` = "requires login".
- No project tests exist yet; none were run.

### Problems and resolutions
- First PowerShell probe returned exit code 128 because the folder is not a git repo; informational, not a failure.
- Web search is not exact-match; name availability results are weak evidence (documented in BRAND_NAME_SHORTLIST.md).
- Four candidate names (Praxon, Zerith, Vaelor, Strova) were found to be in use and were rejected.
- Not completed in this session: full reading of the GitHub webhook doc page, the full Qodo review-tool page, tree-sitter Python binding verification, dataset license checks. These are listed as follow-ups in REFERENCE_RESEARCH.md.

### Current state
Documentation set exists and is internally consistent as of writing. Nothing is implemented or verified beyond the research facts above.

### Pending work
Owner review and answers; brand selection; M1 start.

### Next steps
1. Owner reviews the documents and answers Q1-Q8.
2. On approval: Phase 1 / M1 (monorepo, Docker Compose, CI) with a new session entry.

### Questions and assumptions requiring owner approval
- Q1 Layout deviations in ARCHITECTURE.md section 4 (uv workspace, generated TS client, defer review-sdk).
- Q2 Celery vs Arq for the queue (recommend Celery).
- Q3 LLM provider(s) and a monthly cost ceiling for development; does the owner have API keys? (Recommend starting with one provider plus a local/free option for tests, e.g. the owner's FreeLLMAPI router for personal dev only.)
- Q4 Backend hosting target (Fly.io, Railway, Render, or a VPS with Docker Compose) and domain situation.
- Q5 Will the owner register a GitHub App for development (needed from M2) and on which GitHub account?
- Q6 Retention default of 30 days (ED-012) acceptable?
- Q7 Is this a portfolio/learning project, a startup, or a course submission? It changes priority between ML evaluation depth and product polish.
- Q8 Repository: private or public, and the GitHub account/org name (affects licensing choice and CI).
- Assumption: development happens on this Windows machine with Docker Desktop; Linux containers run the worker.
- Assumption: first release targets GitHub.com only, Python and JS/TS first, Go after.

### Session 1 final summary (appended 2026-11-15 17:13 IST, clock reading)
Owner asked to save everything and continue later. State at pause:
- Done: Phase 0 documents (13 files) written; research and naming exercise done; report delivered. No code, no git repo, nothing installed in the project.
- Awaiting from owner: answers to Q1-Q8 (above) and a brand shortlist choice.
- Where to resume: read PROJECT_RULES.md, this file, ROADMAP.md, ENGINEERING_DECISIONS.md. Then:
  1. Get owner answers to Q1-Q8 and mark ED-001..ED-013 Accepted or changed (append, do not rewrite).
  2. Quick checks before M1: `docker info` (is the daemon running?), `docker compose version`, free disk.
  3. Start M1 (monorepo, uv + pnpm workspaces, Docker Compose with pgvector Postgres and Redis, API health endpoints, Alembic init, lint/type/test setup, GitHub Actions). New session entry, git init on a feature branch, commits authored only by Bhuvan Somisetty, no AI attribution.
  4. Optional in parallel: finish reading the GitHub webhook doc page and Qodo review page, verify tree-sitter Python bindings, check licenses of candidate datasets, search names 11-20, check domains/trademarks for the 2-3 finalists.

---

## Session 2 — 2026-11-16

### Time
Start about 03:23 IST (clock reading 2026-11-16 03:23:53 +05:30).

### Objective
Begin Phase 1 / M1 (engineering foundation). Owner instruction: start Phase 1, no AI attribution anywhere.

### Work completed so far
- Read PROJECT_RULES.md and SESSION_LOG.md. Identity carried over from Session 1: Bhuvan Somisetty.
- Checks: Docker daemon was NOT running (npipe error); Docker Compose v5.3.1 present; `uv` not installed; free disk 12.9 GB (was 14.2 GB).
- Found the old project folder is inside OneDrive. Owner chose (via prompt) to create the repo OUTSIDE OneDrive: `C:\Users\BHUVAN\dev\pr-intel`. The OneDrive folder keeps the Phase 0 docs as a backup copy; nothing there was deleted.
- Owner chose to use my recommended defaults for Q1-Q8: Celery + Redis, uv workspace, generated TS client from OpenAPI, defer review-sdk, 30-day retention, private repo, GitHub.com only first (Python and JS/TS, then Go). Recorded as accepted-by-default; changeable.
- Owner asked about naming: product name is still not chosen; repo/folder `pr-intel`, package `printel` are temporary. No GitHub remote will be created until the name is chosen.
- Created `C:\Users\BHUVAN\dev\pr-intel`, copied PROJECT_RULES.md and docs/, `git init -b develop`, local git identity set to Bhuvan Somisetty <somisettybhuvan5@gmail.com>.
- Installed `uv` 0.13.8 with `python -m pip install --user uv`.
- Started Docker Desktop (daemon readiness not yet verified).

### Technical decisions
ED-001 to ED-013 now Accepted by default (owner approved recommended defaults on 2026-11-16). Repo lives outside OneDrive (new decision ED-014).

### Pending
Verify Docker daemon, scaffold M1, run tests, commit on a feature branch.

### Session 2 progress: backend foundation (appended 2026-11-16, IST clock readings from this session ~03:25-03:55)
- Created: uv workspace (`pyproject.toml`, `uv.lock`), `packages/printel` (config, JSON logging with secret scrubbing and correlation id, SQLAlchemy base, Celery app + `printel.ping` task), `apps/api` (FastAPI: /healthz, /readyz, /version, request-id middleware), `apps/worker` (Celery entry), Alembic (root `alembic.ini`, migration 0001 enables pgvector), `docker-compose.yml` (pgvector/pg16, redis:7, migrate, api, worker, all with healthchecks), `infrastructure/docker/Dockerfile.python`, `.env.example`, `.gitignore`, `.dockerignore`, `.editorconfig`, `.gitattributes`, tests (10 unit, 5 integration).
- Verified (actual outcomes): `ruff check` clean, `ruff format --check` clean, `mypy --strict` no issues in 13 files, `pytest tests` 15 passed. Alembic upgrade head -> downgrade base -> upgrade head all succeeded, `alembic current` = 0001. `docker compose up -d`: db, redis, api, worker healthy, migrate exit code 0. `GET /readyz` returned `{"status":"ready","checks":{"database":true,"redis":true}}`. A task sent from the host was received and executed by the containerized worker: result `pong` (SUCCESS).
- Problems and root causes (kept for the record):
  1. Lint: line-length errors and S105/S106 false positives on test fixtures. Fix: ruff format; tests ignore S105/S106.
  2. `pyproject.toml` failed to parse after a PowerShell edit: Windows PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM. Fix: removed the BOM. Rule: edit files with the editor tools or Python/sed, not `Set-Content -Encoding utf8`.
  3. mypy: Celery has no stubs, so the task decorator is untyped. Fix: one narrow `# type: ignore[untyped-decorator]`.
  4. Integration tests hit the WRONG Postgres: a native Windows `postgres` process (pid 7228) owns host port 5432. Fix: project DB on host port 5433 (`PRINTEL_DB_PORT`). I did not touch that local Postgres.
  5. Docker image had no `alembic`: `uv sync` in a workspace installs only the root package. Fix: `uv sync --frozen --no-dev --all-packages`.
  6. Worker round trip first FAILED and the earlier Redis check was misleading: host port 6379 is owned by `wslrelay` forwarding to a Redis 8.0.5 inside WSL, not our container. The three `printel.ping` task messages I sent while diagnosing went to THAT Redis (list `celery`) and may still be sitting there; owner informed. Fix: project Redis on host port 6380 (`PRINTEL_REDIS_PORT`); added a test asserting the Redis behind the URL is version 7.x so a port clash cannot pass silently.
- Observations (not yet fixed): uvicorn access logs are plain text, not JSON (our JSON logger covers app logs only). A warm worker round trip from the host took about 7.3 s including Python startup; the first task took about 19 s (cold start). Starlette TestClient warns that `httpx` is deprecated in favor of `httpx2`; unresolved.
- Decision ED-015: dev host ports are 5433 (Postgres) and 6380 (Redis) because 5432 and 6379 are taken on this machine.

### Session 2 progress: web scaffold and CI (2026-11-16, IST)
- Owner asked for naming ideas and suggested "Inspector". Searched: crowded in our niche (see BRAND_NAME_SHORTLIST.md). Recommended coined brand + "inspector" descriptor; four new coined names proposed but not yet searched. Name still NOT chosen.
- Web scaffold: `pnpm dlx create-next-app` (Next 16.4.6, React 19.3.0, Tailwind 4.3.3, TypeScript, ESLint, App Router, src dir) into `apps/web`; took about 6 minutes. Removed the template README, the unused template SVGs and the framework-generated `AGENTS.md` (now gitignored since the dev server regenerates it; it addresses AI tools, which the project keeps out of the repo). Replaced the template page with a neutral empty-state page; product name read only from `src/lib/brand.ts`; design tokens: graphite background, warm off-white text, crimson accent, `prefers-reduced-motion` respected.
- `apps/web` stays a self-contained pnpm project with its own lockfile (the generated nested `pnpm-workspace.yaml` only sets `allowBuilds`); a root pnpm workspace is deferred until shared TS packages exist.
- Added `.github/workflows/ci.yml` (python job with pgvector Postgres + Redis services and a started worker; web job: lint, tsc, test, build), `.pre-commit-config.yaml`, `README.md`. YAML syntax validated locally with PyYAML. CI has NOT been run on GitHub (no remote exists), so it is unverified.
- Mistake caught: a `Start-Process pnpm` call failed (pnpm is a .ps1) but my echo said "started"; I corrected it and ran the install as a real background command.

### Session 2: clean-clone verification (2026-11-16 ~04:15 IST)
- Web commit 1da025a. Web checks in the working tree, all exit 0: eslint, `tsc --noEmit`, vitest (1 test), `next build` (2 static routes).
- Clean clone at C:\Users\BHUVAN\dev\_cleanclone (outside the repo, throwaway), Python steps all exit 0: uv sync --frozen --all-packages, ruff check, ruff format --check, mypy (13 files), alembic upgrade/downgrade/upgrade, pytest 15 passed.
- Renamed `vitest.config.ts` to `.mts`; Vite still prints a warning about `configLoader: 'native'` (not yet investigated; harmless so far).
- Correction: an earlier memory-log line said "5 commits"; the real count at that time was 4.

### Session 2: bug found by the clean-clone check (2026-11-16 ~04:30 IST)
- Clean-clone web run: eslint 0, vitest 0, build 0, but `tsc --noEmit` exit 2 (`src/app/layout.tsx(21,50): error TS2304: Cannot find name 'LayoutProps'`). It had passed in the working tree only because earlier builds had generated `.next/types` and `next-env.d.ts` (both gitignored).
- Root cause: `LayoutProps` is a type generated by Next.js; a fresh checkout does not have it until `next typegen` runs. The CI step `tsc --noEmit` would have failed on GitHub.
- Fix (commit a6c2b56): `typecheck` script is now `next typegen && tsc --noEmit`; CI calls `pnpm typecheck`. Verified: on a clone with the generated files renamed away, `pnpm typecheck` exits 0.
- Web steps on the clean clone now: install --frozen-lockfile 0, eslint 0, typecheck 0 (after fix), vitest 0, build 0.
- Note: a PowerShell call with `Remove-Item` was blocked by the tool's path protection; nothing in it ran. For the re-test I renamed the generated files in the throwaway clone instead of deleting.
- Still unverified: an actual GitHub Actions run (no remote).

### Session 2: rename to Lyvern (2026-11-16 IST)
- Owner chose the product name Lyvern. Renamed: `packages/printel` -> `packages/lyvern` (module `lyvern`), `printel_api` -> `lyvern_api`, `printel_worker` -> `lyvern_worker`, env prefix `PRINTEL_` -> `LYVERN_`, Compose project and DB user/name `lyvern`, default display name "Lyvern" (config `product_name`, web `src/lib/brand.ts`). `uv.lock` regenerated. History files (this log, ED-001..ED-016, brand shortlist) keep the old names on purpose. New decision ED-017.
- Before the rename I stopped the old `pr-intel` stack with `docker compose down -v` (removed its dev DB volume `pr-intel_dbdata`, created this session, it only held the pgvector extension).
- Verified after rename (exit codes): ruff 0, ruff format 0, mypy 0 (13 files), pytest 15 passed (including the real worker round trip and the Redis-version guard), compose: db/redis/api/worker healthy, migrate exit 0, `/readyz` ready; web: lint 0, typecheck 0, vitest 0, build 0.
- Next: rename the local folder pr-intel -> lyvern, create the PRIVATE GitHub repo `lyvern` under bhuvan-somisetty, push, watch the first real CI run.

### Session 2: first GitHub Actions run and a requirement change (2026-11-16 IST)
- CI run 43774047610 on phase-1/foundation: web job success. Python job: every real step succeeded (uv sync, ruff, format, mypy, alembic up/down/up, worker start, pytest 15 passed on GitHub's runner) but the job was marked failed because `Post Run astral-sh/setup-uv@v5` (cache pruning) ran about 5 minutes and exited 2.
- Hypothesis (NOT yet verified): the backgrounded `uv run celery` keeps a uv process alive that holds the uv cache lock, so the post-job prune waits then fails. Change: start the worker from `.venv/bin/celery` and add an `if: always()` step that stops it. Will be verified by the next CI run.
- Owner sent a new, fuller product brief (inline + general comments, REQUEST_CHANGES, APPROVE when criteria are met, ML for an AIML internship resume, "very accurate"). It changes ED-006: the bot may now submit APPROVE and REQUEST_CHANGES. Recorded as ED-018 with safeguards (APPROVE off by default per repo, only on a fully succeeded run, labelled automated, branch protection authoritative, uncorroborated LLM findings can never block). PROJECT_RULES, PRODUCT_SPEC and SECURITY updated to match.
- Honesty note recorded for the resume goal: no accuracy figure may be quoted until the benchmark harness has produced it; the harness is part of the build.

### Session 2: engine core, part 1 - contracts and diff parser (2026-11-16 IST)
- Added `lyvern.engine.contracts` (Severity, Category with `bug` per the new brief, Origin, ReviewEvent, RunStatus, frozen `Finding`). Invariants enforced in the type: evidence required, line_end >= line_start, confidence in [0,1], an uncorroborated LLM observation or ML prediction can never be `blocking`. `Finding.fingerprint` ignores line numbers and wording so recurrence survives code movement.
- Added `lyvern.engine.diff`: `parse_patch` (one file, GitHub patch), `parse_git_diff` (full diff incl. renames, binary, quoted paths), `apply_hunks`, exact GitHub `position`, `line`/`side` commentable sets. Hunk ends are decided by header counts, not prefixes; inconsistent input raises `DiffParseError` (file becomes "not analyzed"; no guessed line numbers).
- Tests (`tests/unit/test_engine_diff.py`): 12 hand-written fixtures, plus two property tests that run REAL `git diff --no-index` on generated file pairs (120 + 120 examples) and check: applying parsed hunks to the old file reproduces the new file exactly, every added line number holds the right text, every GitHub position maps to the right raw patch line, additions counted match.
- Generator coverage measured (300 draws): 236 non-empty diffs, 152 with no-newline markers, 210 with deletions, 197 with additions, 95 with zero context, 22 multi-hunk (so the second sparse-edit property test was added to raise multi-hunk coverage).
- Mutation check: deliberately changed the added-line number to `new_no + 1`; the tests failed immediately; restored; 18 pass.
- Problems: my first lint-fix script crashed on a regex escape and applied nothing (the following test run was therefore against unfixed code; caught because ruff still reported errors); redone with plain string replacement. One of my own test expectations was wrong (patch position 5 should be 4); fixed in the test, not the code.
- Verified now: ruff 0, mypy --strict 0 (16 files), pytest tests/unit 28 passed before the last lint tidy, diff tests 18 passed after restore.
