# SESSION_LOG

Append-only. Never edit or delete past entries; correct with a new line under the old one. Timestamps are real system-clock readings in IST (+05:30). No secrets in this file.

## Current status (update at every milestone)
- Last updated: 2026-11-15 17:11 IST (clock reading), Session 1.
- Phase: 0 (Product foundation) written, **awaiting owner approval**. Phase 1 has NOT started.
- Code written: none. Git repo: not initialized. Dependencies installed in the project: none.
- Documents present: PROJECT_RULES.md and 12 files in docs/ (see Session 1 list; this file and CHANGELOG.md included).
- Open questions for owner: see "Questions and assumptions" in the Session 1 report (Q1-Q8 below).
- Next planned action: owner reviews docs, picks answers to Q1-Q8 and a brand shortlist, then Phase 1 (M1) begins.

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
