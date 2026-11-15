# ARCHITECTURE

Status: proposal v0.1, awaiting owner approval. Nothing here is implemented.

## 1. Shape: modular monolith + separate async workers
```
GitHub --webhook--> [api: FastAPI] --enqueue--> [Redis] --> [worker: Celery]
                        |   ^                                  |
                        v   |                                  v
                   [PostgreSQL + pgvector] <-------------- engine/* libraries
                        ^
                        |
                 [web: Next.js dashboard]  (talks only to api)
```
- `apps/api`: HTTP only. Verifies webhook signatures, persists the delivery, enqueues, returns 202 fast. Also serves the dashboard REST API and auth.
- `apps/worker`: runs review jobs. Heavy dependencies (tree-sitter grammars, Semgrep, embedding models) live here, not in the API image.
- `engine/*`: pure Python libraries (no network, no DB): diff parser, code intelligence, static-analysis adapters, review orchestrator, risk engine, semantic search interface. Imported by the worker (and by tests/benchmarks). This keeps them independently testable.
- `ml/`: training and evaluation scripts, datasets manifests, experiment outputs. Trained artifacts are versioned files referenced by a model registry table, never imported from notebooks.
- No microservices at the start. A service is extracted only when a measured need (scaling, isolation, dependency conflict) exists.

## 2. Review pipeline (Module G)
1. **Ingest**: webhook -> verify HMAC-SHA256 (`X-Hub-Signature-256`, constant-time compare, raw body) -> insert `webhook_deliveries` with unique `X-GitHub-Delivery` id (dedup) -> enqueue `review_run`.
2. **Fetch**: installation token (short-lived, scoped to the repo) -> PR metadata, files, patch text, base/head blobs for changed files, with size caps.
3. **Parse diff** (B): per-file hunks, added/deleted line maps, renames, binary/generated/vendored skip list. Unsupported or oversized files become explicit "not analyzed" records.
4. **Understand code** (C): language adapter parses base and head versions, extracts symbols (functions, classes, imports), maps changed lines to enclosing symbols, resolves cross-file references where possible (import graph and name-based call graph; limitations reported).
5. **Static analysis** (D): run Semgrep, Ruff, ESLint, secret scan, dependency audit on the checked-out head tree in a restricted worker environment; normalize to the finding model; keep only findings that touch changed lines or changed symbols (configurable).
6. **ML** (E): finding classification, similarity retrieval of past findings (pgvector), risk features.
7. **LLM** (F): only for what deterministic tools cannot do: cross-file reasoning, explanations, fix suggestions. Context is token-budgeted, secrets redacted, repository text delimited as untrusted data. Output must validate against a JSON schema or it is discarded.
8. **Merge** (G/H): normalize, deduplicate (same file/line/category or near-duplicate text), rank (severity x confidence x touched-line), compute PR risk with factor breakdown, drop findings without evidence or with invalid locations.
9. **Publish**: one GitHub review with `event=COMMENT`, inline comments on validated changed lines (`commit_id` = head SHA at analysis time), summary body. If the head SHA moved, skip stale inline comments.
10. **Persist**: findings, sources, LLM calls and cost, timings, audit entries.

Each step is a function over typed Pydantic models, so a step can be run and tested alone, and a failed step marks the run `partial` with the reason rather than failing silently.

## 3. Key design decisions (also in ENGINEERING_DECISIONS.md)
- **Task queue: Celery + Redis** with `acks_late`, retry with backoff, and a DB `review_runs` table as the source of truth (the queue is not authoritative). Alternative considered: Arq (async-native, smaller community).
- **Idempotency**: unique `(repository_id, pr_number, head_sha, pipeline_version)` per run; re-delivery of the same webhook does nothing.
- **Concurrency per PR**: a newer `synchronize` cancels or supersedes an in-flight older run.
- **Isolation of untrusted code**: PR code is only read as text and parsed. Static analyzers read files but never execute them; Semgrep/ESLint run with no repo-supplied config trusted (our configs only), in a worker container with no secrets in its environment and limited CPU/memory/time. No `npm install`, no running tests.
- **Parsing**: Python `ast` for precise Python facts, tree-sitter for everything else (error-tolerant, gives byte/line ranges). Language adapters implement one `LanguageAdapter` protocol (`parse`, `symbols`, `imports`, `enclosing_symbol(line)`, `limitations`).
- **Embeddings**: pgvector in the same Postgres to avoid another datastore; model chosen after the E2 benchmark.
- **LLM layer**: `LLMProvider` protocol (`complete(messages, schema, budget) -> result + usage`), implementations behind config. No provider SDK imported outside `lyvern/llm/providers/`.
- **Multi-tenancy**: every tenant table carries `organization_id`; plan to add Postgres row-level security as defense in depth, plus repository-scoped checks in the service layer.

## 4. Proposed deviations from the suggested repository layout (need approval)
| Suggested | Proposed | Reason |
|---|---|---|
| `packages/shared-types` hand-written | Generate TS types/client from the FastAPI OpenAPI schema | Keeps frontend/backend contracts in sync automatically |
| `packages/review-sdk` | Defer; not needed until there is an external consumer | Avoid unnecessary abstraction |
| `engine/` top-level separate from `apps/` | Keep, but make it one installable Python package `lyvern` with sub-packages, managed by a uv workspace | One lockfile, simple imports, still independently testable |
| `infrastructure/github` | Keep as docs + app manifest JSON only | No code needed there |
| `tests/` all at root | Keep root `tests/` for cross-module integration/e2e/security/ml; unit tests live next to each package | Faster feedback and clearer ownership |

## 5. Deployment sketch
- Web: Vercel. API + worker + Postgres + Redis: a container host (candidates: Fly.io, Railway, Render, or a single VPS with Docker Compose). Choice is open question Q4. Local development: Docker Compose for Postgres (pgvector image) and Redis.
- Cross-site auth caveat: if web (Vercel) and api live on different registrable domains, cookie auth breaks; use one parent domain (e.g. `app.` and `api.` subdomains) or proxy the API through Next.js route handlers.

## 6. Observability
Structured JSON logs with `delivery_id`/`review_run_id`, per-step timings stored on the run, LLM token and cost counters, error tracking hook (provider TBD), health and readiness endpoints.

## 7. Known constraints
- Dev machine is Windows 11 with about 14 GB free disk; Docker is installed (daemon state not yet verified), Postgres and Redis are not installed locally and will run in Docker. ML model downloads (embedding models, PyTorch CPU wheels) must be size-budgeted.
- Semgrep OSS output hides matched source lines and fingerprints (`"requires login"`, verified locally with Semgrep 1.161.0); evidence snippets must be read from the checked-out file by our own code.
