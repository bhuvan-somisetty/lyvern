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

### Session 2: engine core, part 2 - policy, decision, dedup, placement, render (2026-11-16 IST)
- Added `engine.policy` (ReviewPolicy, approval OFF by default), `engine.decision` (pure `decide`, `is_blocking`, `mark_blocking`; ED-018), `engine.dedup` (cluster by fingerprint or same file+category+overlapping lines; only trusted sources corroborate; survivor inherits impact/fix text), `engine.placement` (inline only on lines the PR added; both ends of a multi-line comment are added lines in one hunk; unchanged/out-of-diff -> general note or dropped; one comment per line; limit; work bounded by diff size), `engine.render` (plain markdown, no emojis, origin labels, fingerprint markers for cross-run dedup, fence-safe evidence, computed counts only, 60k cap).
- Tests: `tests/unit/test_engine_review.py` 47 tests incl. hypothesis properties over arbitrary findings/state/policy: APPROVE implies opt-in + succeeded run + all stages complete + no blocking + risk and unanalyzed limits; REQUEST_CHANGES implies trusted-or-corroborated, confident, introduced-by-PR blocking findings; inline anchors always land on added lines; nothing lost or duplicated by placement.
- Bugs found by the tests themselves: (1) a property test showed multi-line comments could end on an unchanged context line, contradicting the stated rule; code tightened (both ends added lines). (2) My dedup originally let two LLM findings corroborate each other (not independent evidence); fixed before the tests existed, found by review. (3) Several of my own expected values were stale after rule changes; fixed in tests.
- Mutation checks: making `is_blocking` return True failed 3 tests; removing the "other stage failed" approval obstacle failed 1 test (note: the random invariant test did not catch that one, only the targeted test did; raise example counts or add a targeted strategy later). Restored; 47 pass.
- Local gate: ruff 0, format 0, mypy --strict 0 (21 files), pytest tests/unit 75 passed.
- Limitation to remember: this is the review LOGIC. Nothing yet talks to GitHub, runs analyzers, calls an LLM, or trains a model. No accuracy claim exists or may be made.

### Session 2: CI verified green (2026-11-16 IST)
- GitHub Actions run 43774680130 on commit b87b702 (phase-1/foundation): conclusion success. This verifies the earlier hypothesis: starting the worker from `.venv/bin/celery` and stopping it in an `if: always()` step removed the setup-uv post-job cache-prune failure. Python job (lint, format, mypy, migrations up/down/up, worker, 15 tests) and web job (lint, typecheck, test, build) both passed on GitHub's runners.
- A new run for ca5e283 (engine part 2) was started by the push; its result is not yet recorded here.

### Session 2: documentation set and publishing (2026-11-16 IST)
- Owner asked for PRD, TRD, an A-to-Z project document (features, what is special, why these choices, comparison with similar tools, how the product is used), code visible in the OneDrive folder, and everything pushed to GitHub.
- Wrote `docs/PRD.md`, `docs/TRD.md`, `docs/PROJECT_HANDBOOK.md`; every feature and claim is labelled BUILT / DESIGNED / PLANNED. The handbook example is real output of `render_inline` / `render_summary` on a sample patch; its finding was supplied by hand and the doc says so. Competitor descriptions are limited to what was seen in research and carry a "verify before quoting; no superiority claimed" warning.
- Explained usage to the owner: a GitHub App plus a web dashboard (not a browser extension); install once, open PRs as normal, review appears on the PR; optional local CLI planned.
- README now has status, a code map and doc links; CHANGELOG updated.
- Published: fast-forwarded `develop` to the current work and pushed `develop` and `phase-1/foundation` to https://github.com/bhuvan-somisetty/lyvern (private). Verified via the GitHub API that the default branch now lists apps/, packages/, tests/, the full engine modules and all 15 docs. Attribution check clean; all 23 commits authored only by Bhuvan Somisetty.
- Code visible in the OneDrive folder the owner has open: moved the stale Phase 0 copies into `_phase0_original/` (nothing deleted), then exported a snapshot of tracked files with `scripts/export_snapshot.sh` (git archive; no .git/.venv/node_modules). The git repo at C:\Users\BHUVAN\dev\pr-intel stays the source of truth; the snapshot is for browsing and goes stale until re-exported.
- Doc consistency fixes: ED-018 module name (`lyvern.engine.decision`) and API spec contracts path (`lyvern.engine.contracts`).

### Session 2: real-data check of the diff parser (2026-11-16 IST)
- Fetched (read-only, via the owner's `gh` login) the file lists of the 12 most recent closed PRs of jaegertracing/jaeger-ui and 12 of joinmarket-webui/jam. Ran `parse_patch` on every GitHub patch and compared the parsed additions/deletions with the counts GitHub reports per file.
- Result: 24 PRs, 84 files, 84 parsed, 0 parse errors, 0 files without a patch, 266 hunks, 2734 added lines, 0 addition/deletion count mismatches against GitHub. Caveat: small sample (recent closed PRs only); it checks counts and parseability, not review quality. Note: the scratch script that first tried to do this through Python `subprocess` returned no output in this environment, so the fetch was done with the shell and parsed from saved files.

### Session 2: reviewer mode (CLI) first version (2026-11-16 IST)
- Owner instruction: never post comments or anything on public open-source PRs; any posting tests go in the owner's own repository. Implemented reviewer mode so that it CANNOT write: `lyvern.github.client.GitHubReadClient` has a single primitive that issues GET requests; a unit test inspects the source for write verbs (post/put/patch/delete/request/send/stream), another asserts the public method set is exactly {close, get_pull_request, list_changed_files, get_file_text}, another asserts every recorded request is a GET, and the CLI test asserts the only command is `review`.
- Added: `lyvern.github` (models, `parse_pr_reference` for URLs and owner/repo#N, read client with pagination, retry on 502/503/504, rate-limit error with reset time, content decoding with size cap), `lyvern.engine.analyzers.ruff` (stdin, `--isolated`, curated rule table, evidence from our own source, security rules skipped in test files, noisy rules ignored), `lyvern.review_pipeline` (read PR, parse patches, analyse Python, dedupe/mark/rank/place/decide/render; honest list of not-analysed files; risk stage absent so approval is impossible), `lyvern.cli` (`lyvern review <PR> [--json]`, prints DRAFT, says nothing was posted).
- Tests: +44 (client/refs 25, ruff adapter 11, pipeline/CLI 8 + one more) -> `pytest tests/unit` 119 passed. ruff, format, mypy --strict clean.
- Real-data findings: (1) current Ruff reports syntax errors with the code "invalid-syntax", not null; my first mapping would have reported an unparseable file as INFO/maintainability; caught by a test run on real Ruff output, fixed. (2) The summary label "Files: 0 changed" was misleading on a docs-only PR; renamed to "Source files" and the CLI prints the PR's real size.
- Real runs (read-only GET requests via the owner's gh login): jaeger-ui PR #4787 (docs only: 0 source files, no findings) and three recent closed The-PR-Agent/pr-agent PRs (#4970, #4969, #4968): all analysed, no findings, verdict COMMENT. This shows it does not invent problems on clean PRs; it does NOT yet show that it catches real bugs. No accuracy claim exists.
- Process notes: the shell tool collapses `\n` into real newlines inside heredocs, which twice broke edits that contained escape sequences; use the file-edit tools for content with backslashes. A first full test run took 224 s, later runs 35-53 s (cold start); one Ruff call costs about 1-2 s because the adapter starts one process per file: batching files per PR is a planned optimisation.
- Limits: JS/TS/Go files are listed as "no analyser for this file type yet", so on jaeger-ui and jam PRs (TypeScript) reviewer mode currently reports nothing useful. Next: Semgrep rules for JS/TS, then the benchmark against real human review comments.

### Session 2: owner setup guide (2026-11-16 IST)
- Owner asked for step-by-step instructions for everything they must do. Wrote `docs/SETUP_GUIDE.md` (open the right folder, try reviewer mode, create the `lyvern-sandbox` repo, smee.io tunnel, secrets folder outside OneDrive, GitHub App registration field by field, free AI key options, what to send back and what never to send). Verified the Step 2 commands work as written: `lyvern review <URL>` and `lyvern review owner/repo#N --json` both ran on real public PRs (read-only, posted = False).
- The guide's GitHub UI click paths are from general knowledge of GitHub's current interface, not verified by clicking through it in this session; if a label differs, the owner should tell me and I will correct the guide.

### Session 2: owner setup progress (2026-11-16 IST)
- Owner completed: smee.io channel created, a webhook secret generated, a Google AI Studio (Gemini) API key and a Groq API key created, opened the GitHub App registration form and the new-repository form. Owner ran reviewer mode on a real PR from a terminal opened on the OneDrive snapshot folder (output correct: DRAFT, nothing posted).
- The owner pasted the two API keys and the webhook secret in the chat and asked not to be told to rotate them. They were saved only in `C:\Users\BHUVAN\dev\pr-intel\.env` (git-ignored: `git check-ignore` confirms rule `.gitignore:1`), never in docs, logs, memory or commits. `.env.example` gained the variable NAMES only (LYVERN_GEMINI_API_KEY, LYVERN_GROQ_API_KEY, LYVERN_GITHUB_WEBHOOK_SECRET, LYVERN_SMEE_URL). If webhook signature checks fail later because a character was mis-transcribed from a screenshot, rotate the webhook secret (the secret was read from a terminal screenshot).
- Verified both keys against the providers' model-list endpoints (status only, keys not printed): Groq HTTP 200, 11 models (e.g. openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b); Gemini HTTP 200, 50 models (e.g. gemini-2.5-flash, gemini-2.5-pro, gemini-2.5-flash-lite). Free-tier limits and data-use terms are unverified; only public code may be sent for now.
- Sandbox repo `bhuvan-somisetty/lyvern-sandbox`: GitHub API returned 404, i.e. NOT created yet (form filled but not submitted).
- Seen in the owner's screenshots of the App form: Webhook URL field contained the repository URL instead of the smee address (must be the smee URL); the Pull requests permission and the Pull request event were not yet set (events only appear after permissions are chosen); the GitHub App had not been created yet as far as the screenshots show.
- Side effect to fix: running `uv run` in the OneDrive snapshot folder created a `.venv` (61 packages) inside OneDrive, which will sync. Owner advised to delete it and run commands from C:\Users\BHUVAN\dev\pr-intel.

### Session 2: GitHub App registered (2026-11-16 IST)
- Owner registered the development GitHub App (name lyvern-dev-bhuvan, owned by bhuvan-somisetty, installable only on that account). App ID 5777151, Client ID Iv23liNHA8on66qKdDQ7 (identifiers, not secrets). Screenshots show: Webhook active with the smee.io URL, a webhook secret configured, SSL verification enabled; permissions Pull requests = Read and write, Contents = Read-only, Metadata = Read-only (mandatory); installation scope "Only on this account". Whether the "Pull request" event box was ticked before creation was not visible in the final screenshots; to be verified under the App's "Permissions & events" page.
- Still to do by the owner: generate the private key (save as C:\Users\BHUVAN\secrets\lyvern-dev.pem), create the lyvern-sandbox repository, install the App on that repository only.
- Added ids and the key path (not the key) to the local .env and variable names to .env.example.

### Session 2: GitHub App credentials verified (2026-11-16 IST)
- The owner generated the App's private key; it downloaded into the root of the OneDrive folder (which syncs to the cloud). Moved it (not read or printed) to C:\Users\BHUVAN\secrets\lyvern-dev.pem (1679 bytes, one PEM private-key header line; no copy left in the OneDrive root). Note: OneDrive may have briefly synced it, so a copy may sit in OneDrive's cloud recycle bin; emptying that bin is optional extra hygiene.
- Verified by authenticating to GitHub as the App (RS256 JWT with the App ID and that key, one-off script in the session scratchpad, GET /app and GET /app/installations): authenticated as app lyvern-dev-bhuvan, id 5777151, owner bhuvan-somisetty; permissions {contents: read, metadata: read, pull_requests: write}; subscribed events [pull_request]; installations: 0 (not installed yet). Script uses only read endpoints and prints no secrets.
- Next: owner installs the App on `lyvern-sandbox` only (Only select repositories). Then build the App-side code: webhook receiver with signature verification, installation-token client, review publisher, tested in the sandbox repo only.

### Session 2: App installed and verified (2026-11-16 IST)
- Owner installed the App on the personal account with "Only select repositories": lyvern-sandbox. Verified through the API as the App: 1 installation (id 182407481, account bhuvan-somisetty, selection "selected", events [pull_request], permissions contents:read metadata:read pull_requests:write); a short-lived installation token (minted, never printed) can reach exactly one repository: bhuvan-somisetty/lyvern-sandbox (total_count 1). Installation id saved in the local .env (an identifier, not a secret).
- Decision (enforces the owner's rule in code): the write path is guarded by an allowlist, `LYVERN_WRITE_ALLOWED_REPOS`, default only the sandbox; the publisher raises before any HTTP call for any other repository.

### Session 2: GitHub App building blocks (2026-11-16 IST)
- Added `lyvern.github.webhook` (HMAC-SHA256 over the raw body with constant-time compare; pull_request parsing that extracts only the needed fields; malformed payloads raise), `lyvern.github.app_auth` (RS256 app JWT with a 10-minute lifetime, installation tokens cached in memory with a 2-minute refresh margin, errors never include key material), `lyvern.github.publisher` (explicit review event, `line`/`side`/`start_line`, duplicate-comment skipping through hidden fingerprint markers, refused APPROVE downgraded to COMMENT with a note, rejected inline locations moved into the body, other failures raise) and a `WriteGuard` allowlist that raises before any network call. Settings gained GitHub App, webhook secret, LLM key and write-allowlist fields (secrets as SecretStr).
- Tests: +21 (`tests/unit/test_github_app.py`); `pytest tests/unit` 140 passed; ruff, format, mypy --strict clean.
- Mutation check: replacing the guard condition with `if False:` made 2 tests fail; restored, 21 pass.
- Test bug found: my refresh test used a wrong epoch (01:46:40 vs 02:46:40 UTC for 1e9); the cache logic was right; fixed the data and verified the epoch with Python.

### Session 2: webhook ingestion, review job and database tables (2026-11-16 IST)
- Added tables `webhook_deliveries` (unique delivery id) and `review_runs` (unique repo+PR+head sha) with Alembic migration 0002 (verified: upgrade, downgrade to 0001, upgrade; `alembic current` = 0002).
- Added `POST /webhooks/github` (raw-body HMAC check first: 401 on bad/missing signature, 413 above 5 MB, 400 on malformed payload), `lyvern.services.ingest` (idempotent via the two unique constraints; non-review events and actions are recorded as ignored; repositories outside the write allowlist are recorded as rejected and never queued), `lyvern.services.review_job` (queued -> running -> succeeded/partial/failed/superseded; reads PR, analyses, publishes through the guarded publisher, records event, review id and counts; a newer run for the same PR supersedes an older one; failures are stored without secrets) and Celery task `lyvern.review.run`.
- Tests: +13 integration tests against real Postgres (8 webhook flow, 5 review job); full suite `pytest tests` 158 passed; ruff, format, mypy --strict clean. Mutation check: removing the allowlist check in ingestion made `test_repository_outside_the_write_allowlist_is_never_queued` fail; restored.
- Not yet done: the end-to-end run in the sandbox repository through the smee tunnel (needs API and worker running locally and a test PR created in lyvern-sandbox).

### Session 2: FIRST END-TO-END REVIEW ON GITHUB (2026-11-16 ~07:35 IST, sandbox only)
- Setup: API (uvicorn, port 8010 because 8000 is held by wslrelay), Celery worker (solo pool), smee-client forwarding https://smee.io/<channel> to http://127.0.0.1:8010/webhooks/github, Postgres+Redis from Docker Compose; old compose api/worker containers stopped. Everything ran against the owner's sandbox repo only (write allowlist = bhuvan-somisetty/lyvern-sandbox).
- Test: through the GitHub API (as the owner, in the sandbox) created branch `test/python-issues`, committed `app.py` (11 lines: unused import, mutable default argument, subprocess shell=True, eval, undefined name) and opened sandbox PR #1.
- Observed (real, from logs and the GitHub API): GitHub delivered `pull_request opened` -> smee -> API returned 202 -> row in webhook_deliveries (status queued) -> review run queued -> worker task received and "succeeded in 8.7s" -> review 5914255686 posted by `lyvern-dev-bhuvan[bot]` with state CHANGES_REQUESTED and 5 inline comments: line 11 F821 (undefined `vals`), line 7 S307 (eval), line 6 S602 (shell=True), line 5 B006 (mutable default), line 1 F401 (unused import). Checked against the file fetched back from GitHub: every comment is on exactly the intended line. Review body counts (5 reported: high 3, medium 1, low 1; bug 2, maintainability 1, security 2; 5 inline, 0 general) match the findings; blocking findings listed: F821 and S307; S602 not blocking (confidence 0.75 < 0.8 threshold). DB run row: succeeded | REQUEST_CHANGES | findings 5 | inline 5 | review id 5914255686.
- Caveats: this is one hand-made PR with deliberate problems; it shows the pipeline works, not that it is accurate on real code. No false-positive/recall measurement exists yet. Only Python is analysed.
