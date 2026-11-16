# Lyvern: Technical Requirements Document (TRD)

Version 1.0, 2026-11-16. Companion to `PRD.md`, `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `API_SPECIFICATION.md`, `ML_DESIGN.md`, `SECURITY.md`.
Status labels: **BUILT** (implemented and verified by tests), **DESIGNED** (specified, not implemented), **PLANNED** (intended).

---

## 1. System overview
Modular monolith plus asynchronous workers. A FastAPI service receives GitHub webhooks and serves the dashboard API; a Celery worker runs review jobs; PostgreSQL (with pgvector) stores state; Redis carries jobs. A pure-Python review engine (`lyvern.engine`) holds all review logic and has no network or database access, so it can be tested exhaustively.

```
GitHub --webhook--> API (FastAPI) --enqueue--> Redis --> Worker (Celery)
                       |                                   |
                       v                                   v
                 PostgreSQL + pgvector  <----------  engine (pure logic)
                       ^
                 Dashboard (Next.js)
```

| Component | Location | Status |
|---|---|---|
| Shared core (settings, JSON logging with secret scrubbing, DB base, Celery app) | `packages/lyvern` | BUILT |
| HTTP API: `/healthz`, `/readyz`, `/version`, request-id middleware | `apps/api` | BUILT |
| Worker entry (`lyvern.ping` task) | `apps/worker` | BUILT |
| Migrations (Alembic; enables pgvector) | `packages/lyvern/.../migrations` | BUILT |
| Docker Compose stack (db, redis, migrate, api, worker) with healthchecks | `docker-compose.yml` | BUILT |
| CI (lint, format, strict types, migrations up/down/up, tests, web build) | `.github/workflows/ci.yml` | BUILT, green on GitHub |
| Review engine: contracts, diff, dedup, placement, decision, render, policy | `packages/lyvern/src/lyvern/engine` | **BUILT** |
| Read-only GitHub client (`lyvern.github`), reviewer-mode pipeline and CLI (`lyvern.review_pipeline`, `lyvern.cli`), Ruff adapter | `packages/lyvern` | **BUILT** |
| Webhook endpoint (`/webhooks/github`), idempotent ingestion, review job, guarded publisher, DB tables `webhook_deliveries` and `review_runs` | `apps/api`, `lyvern.services`, `lyvern.github` | **BUILT**, verified end to end in the sandbox repository |
| Static-analysis adapters, code intelligence, ML, LLM, orchestrator | `lyvern.engine.*` | PLANNED |
| Dashboard pages | `apps/web` | shell BUILT; pages PLANNED |

## 2. Technology choices and rationale
| Choice | Why | Alternatives considered |
|---|---|---|
| **GitHub App** (not an extension, Action, or OAuth app) | Installs once per account/repo, gets webhooks, short-lived scoped tokens, can post reviews as its own identity, fine-grained permissions | Browser extension (runs only in one user's browser, no automation); GitHub Action (runs per repo workflow, secrets sprawl, no central history); OAuth app (acts as a user, broader access) |
| **Python 3.12 + FastAPI + Pydantic v2** | Best ecosystem for ML, tree-sitter, Semgrep integration; typed validation at every boundary | Node/TypeScript (weaker ML/analysis tooling), Go (fast but small ML ecosystem) |
| **PostgreSQL + pgvector** | One datastore for relational data and embeddings; fewer moving parts | Separate vector DB (Pinecone/Qdrant/FAISS service): extra infrastructure before scale demands it |
| **Celery + Redis** (DB is source of truth) | Mature retries/ack-late/scheduling | Arq (async-native, smaller community), RQ (weak retry story) |
| **tree-sitter + Python `ast`** | Error-tolerant parsing across languages with exact line ranges; `ast` for exact Python semantics | Regex heuristics (inaccurate), language servers (heavy) |
| **Semgrep, Ruff, ESLint, secret scanner, dependency audit** | Reuse proven deterministic tools; give verifiable evidence | Writing our own rules (unrealistic, lower quality) |
| **uv workspace** | Fast reproducible Python monorepo with one lockfile | pip/poetry |
| **Next.js + Tailwind** | Standard, deployable on Vercel, strong typing | Plain React SPA |
| **Property-based testing against real `git diff`** | Strongest oracle available for the diff parser | Hand-written fixtures only |

## 3. Review pipeline (DESIGNED end to end; engine stages BUILT)
1. **Ingest (PLANNED):** verify `X-Hub-Signature-256` over the raw body (HMAC-SHA256, constant-time compare); insert delivery id (`X-GitHub-Delivery`) with a unique constraint; return 202; enqueue.
2. **Fetch (PLANNED):** installation token (short-lived, repo-scoped); PR metadata, changed files and patches, base/head file contents, existing review comments. Size caps; failures mark files "not analyzed".
3. **Parse diff (BUILT):** `lyvern.engine.diff`.
4. **Understand code (PLANNED):** symbol extraction, imports, call graph, cross-file callers; unsupported languages reported.
5. **Static analysis (PLANNED):** run analysers on the head tree in a restricted subprocess (timeouts, memory caps, no network, our configs only); normalise to `Finding`; evidence read from our own file reads (Semgrep OSS output hides matched lines: verified).
6. **ML (PLANNED):** classification, similarity retrieval, risk factors.
7. **LLM (PLANNED):** only for what tools cannot do; untrusted-data delimiting; redaction; JSON-schema validated output; discard on invalid.
8. **Merge (BUILT):** `dedupe` then `mark_blocking` then `rank`.
9. **Place (BUILT):** `plan_placement` → inline / general / dropped.
10. **Decide (BUILT):** `decide` → event + reasons.
11. **Render (BUILT):** `render_inline`, `render_summary`.
12. **Publish (PLANNED):** one review via the GitHub API; skip comments already posted (fingerprint markers); handle stale head SHA.
13. **Persist (PLANNED):** run, findings, comment ids, timings, cost, audit entries.

Each step is a function over typed models so it can be tested alone; a failed step makes the run `partial` and the review says so.

## 4. Data contracts (BUILT: `engine/contracts.py`)
`Finding` (frozen, validated): category (`bug`, `security`, `performance`, `maintainability`, `reliability`, `testing`, `documentation`), severity (`critical`..`info`), confidence 0-1 (separate from severity), origin (`static_analysis`, `ml_prediction`, `llm_observation`, `human_confirmed`), detection_source, file_path, line range, title, description, **evidence (required)**, impact, recommended_fix, `introduced_by_pr`, `blocking`, `corroborated_by`.
Invariants enforced by the type: evidence non-empty; end >= start; an uncorroborated LLM or ML finding can never be `blocking`. `fingerprint` (hash of category, file, source, normalised evidence) is stable when lines move.

## 5. Diff handling (BUILT: `engine/diff.py`)
- Parses GitHub per-file patches and full `git diff` (renames, binary, quoted paths, `\ No newline`).
- Hunk end is decided by header counts, not line prefixes, so content like `--- foo` cannot be misread.
- Malformed or truncated input raises `DiffParseError`; the file becomes "not analyzed" (no guessed line numbers).
- Exposes added lines, commentable lines per side, and the GitHub `position` (0-based index within the file's patch, first `@@` = 0).
- **Verification:** two property tests run real `git diff --no-index` on generated file pairs (random edits, sparse edits, tricky content) and check that applying parsed hunks reproduces the new file exactly, that added line numbers hold the right text, and that positions point at the right raw patch line. A deliberate off-by-one in the parser was caught.

## 6. Placement rules (BUILT: `engine/placement.py`)
Inline comments only on lines the PR added and GitHub accepts; both ends of a multi-line comment are added lines within one hunk; anything else is a general note (if introduced by the PR) or dropped (pre-existing); at most one comment per line; configurable cap; INFO and below-threshold findings go to the summary; work is bounded by diff size, never by a model-supplied line range.

## 7. Decision engine (BUILT: `engine/decision.py`, `engine/policy.py`; ED-018)
Pure function `decide(findings, state, policy) → Decision(event, publish, incomplete, blocking, reasons)`.
- **Blocking** requires: severity in policy set (default critical/high), introduced by the PR, confidence >= threshold (default 0.8), and a trusted basis (static analysis or human, or corroboration by a trusted source).
- **REQUEST_CHANGES** if any blocking finding and the repo allows it.
- **APPROVE** only if the repo opted in (default off), the run succeeded, every stage completed, required stages present, unanalysed-file share within limit, risk known and below ceiling, and no medium-or-higher PR-introduced finding. Otherwise COMMENT with the reasons.
- A failed run produces a neutral "could not complete" comment; a superseded run publishes nothing.
- **Verification:** 400-example property test over arbitrary findings/state/policy asserts the safety properties; targeted tests; mutation checks (making LLM findings blockable, removing the failed-stage check) were caught.

## 8. GitHub integration (DESIGNED; PLANNED to build)
- **Events:** `pull_request` (opened, reopened, synchronize, ready_for_review, closed), `installation`, `installation_repositories`; later review-comment events for feedback.
- **Permissions (minimum):** Metadata read; Pull requests read/write; Contents read. No Actions/Admin/Secrets. Checks write only if check runs are added.
- **Publishing:** one `POST /repos/{owner}/{repo}/pulls/{n}/reviews` with `commit_id` = analysed head SHA, `event` from the decision engine, a body (summary), and `comments[]` using `path`, `line`, `side`, and `start_line`/`start_side` for ranges. If the head moved, stale inline comments are skipped. Rate limits honoured via `Retry-After` / `x-ratelimit-reset`. Review and comment ids stored; existing fingerprints read back to avoid duplicates across runs.
- **Approval reality check (to be verified empirically):** GitHub does not let an author approve their own PR, and an App's approval may not count toward required reviews depending on repository rules. If refused or ignored, the system reports it and downgrades to COMMENT. It never pretends a comment is an approval.

## 9. Security (BUILT where marked; rest DESIGNED, see `SECURITY.md`)
- Untrusted inputs: all repository content, PR text, filenames, diffs.
- Log scrubbing of secret-like keys and token shapes: BUILT and tested.
- Secrets in config use `SecretStr`; never in repr/logs: BUILT and tested.
- Never execute PR code in app processes; analysers parse text only in a restricted subprocess: DESIGNED.
- Secret redaction before any LLM call; model has no tools; schema-validated output; injection test corpus: DESIGNED.
- Tenant isolation (`organization_id` everywhere, Postgres row-level security planned): DESIGNED.
- Webhook HMAC verification, delivery dedup, least-privilege App permissions: DESIGNED.

## 10. ML and AI (DESIGNED; nothing trained yet; no metric exists)
See `ML_DESIGN.md`. Summary: baselines first; leakage-safe splits (group by repository, time-based); report precision/recall/F1, confusion matrix, Precision@K, calibration with sample sizes; risk score starts as an explainable rule model and becomes learned only with a defensible label. LLM output is always `llm_observation` and can never block without independent corroboration.

## 11. Reliability and performance (DESIGNED)
Idempotency by unique `(repository, PR, head SHA, pipeline version)`; newer commits supersede older runs; retries with backoff; partial runs labelled; per-step timings stored; analyser timeouts; size caps. No performance numbers are claimed; latency/cost will be measured on the benchmark.

## 12. Testing and verification status (facts as of 2026-11-16)
| Layer | Result |
|---|---|
| Lint, format, strict typing | ruff, ruff format, mypy --strict clean locally and in CI |
| Unit tests | 75 passed on the latest local run (diff parser 14 test functions incl. 2 real-git property tests; review logic 41; platform 10) |
| Integration tests | 5 (database, Redis identity/version, pgvector, worker round trip through Redis); passing at last run |
| Migrations | up, down, up verified locally and in CI |
| Containers | db, redis, api, worker healthy; `/readyz` ready; real worker round trip returned `pong` |
| CI on GitHub | green on commit `93bd560` (and `b87b702`) |
| Web | eslint, typecheck, vitest, production build pass |
| Not yet tested | Anything touching real GitHub, analysers, LLMs, ML models, dashboard flows |

## 13. Deployment and operations (PLANNED)
Frontend on Vercel; API/worker/Postgres/Redis on a container host or VPS with Docker Compose; migrations as a job; secrets from the platform store; structured JSON logs with correlation ids; health and readiness endpoints exist (BUILT).

## 14. Constraints and known limitations
- Development machine ports: Postgres host 5433 and Redis 6380 (5432 and 6379 are taken locally); a test asserts the Redis version so clashes cannot pass silently.
- Semgrep OSS offline JSON omits matched lines and fingerprints (observed locally): evidence must come from our own file reads.
- uvicorn access logs are not JSON yet.
- No accuracy claim exists or may be made until the benchmark produces one.
