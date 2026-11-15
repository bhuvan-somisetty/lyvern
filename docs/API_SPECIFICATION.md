# API_SPECIFICATION

Status: design v0.1. FastAPI generates the authoritative OpenAPI document at `/openapi.json`; the TypeScript client for `apps/web` is generated from it. This file is the human-readable contract. Base path `/api/v1`. JSON only. Errors use `{"error": {"code": "...", "message": "...", "request_id": "..."}}`. List endpoints use cursor pagination (`limit` max 100, `cursor`).

## 1. Webhook (public, signature-verified)
| Method | Path | Notes |
|---|---|---|
| POST | `/webhooks/github` | Headers: `X-GitHub-Event`, `X-GitHub-Delivery`, `X-Hub-Signature-256`. Verifies the signature over the raw body first (401 on failure, no body parsing). Duplicate delivery id returns 200 `{"status":"duplicate"}`. Valid events return 202 after persisting and enqueueing. Body size capped. |

Handled events: `pull_request` (`opened`, `reopened`, `synchronize`, `ready_for_review`, `closed`), `installation` (`created`, `deleted`, `suspend`, `unsuspend`), `installation_repositories` (`added`, `removed`). Others are stored as `ignored`.

## 2. Auth
| Method | Path | Notes |
|---|---|---|
| GET | `/auth/github/login` | Starts OAuth (state + PKCE) |
| GET | `/auth/github/callback` | Creates session cookie |
| POST | `/auth/logout` | |
| GET | `/me` | Current user, organizations, roles |

## 3. Organizations and repositories
| Method | Path |
|---|---|
| GET | `/organizations` |
| GET/PATCH | `/organizations/{org_id}` (retention_days, external_llm_enabled) |
| GET | `/organizations/{org_id}/repositories` |
| GET/PATCH | `/repositories/{repo_id}` and `/repositories/{repo_id}/settings` |
| POST | `/repositories/{repo_id}/disconnect` |
| DELETE | `/repositories/{repo_id}/data` (purge, owner/admin only, audited) |

## 4. Pull requests and reviews
| Method | Path |
|---|---|
| GET | `/repositories/{repo_id}/pull-requests` (filters: state, author, risk_level) |
| GET | `/pull-requests/{pr_id}` |
| GET | `/pull-requests/{pr_id}/reviews` (run history) |
| GET | `/reviews/{run_id}` (status, step timings, limitations, risk factors) |
| POST | `/reviews/{run_id}/rerun` (admin/member; rate limited) |
| GET | `/reviews/compare?a=&b=` (diff findings between two runs) |

## 5. Findings
| Method | Path |
|---|---|
| GET | `/findings` (filters: repository, severity, category, origin, status, q full-text, date range) |
| GET | `/findings/{id}` |
| POST | `/findings/{id}/feedback` body `{verdict, reason?}` |
| PATCH | `/findings/{id}` body `{status}` (resolve, dismiss, confirm) |
| GET | `/findings/recurring` (grouped by fingerprint) |
| POST | `/exports` body `{format: csv|json|sarif, filters}` returns a download URL |

## 6. Analytics
`GET /analytics/overview`, `/analytics/trends`, `/analytics/risk`, `/analytics/quality` (precision from feedback, with `n` and confidence interval), `/analytics/usage-cost`, `/analytics/ml` (model metrics from `ml_evaluations`). Every response includes counts so the UI can show "not enough data" instead of a number.

## 7. System
`GET /healthz` (liveness), `GET /readyz` (DB + Redis), `GET /version`.

## 8. Cross-cutting
- Authorization: every route derives `organization_id` from the session and the resource; cross-org access returns 404, not 403.
- Rate limits: per-IP on auth and webhooks, per-user on reads and writes, tighter on `rerun` and `exports`.
- Idempotency: `rerun` accepts `Idempotency-Key`.
- Versioning: breaking changes need `/api/v2`; additive fields are allowed.
- Pydantic v2 models define all request and response bodies; unknown request fields are rejected.

## 9. Internal contract (engine <-> worker)
`ReviewJob` (ids, installation, repo, PR number, head/base sha, pipeline_version) -> `ReviewResult` (findings[], risk, limitations[], llm_usage[], timings). Defined once in `lyvern.contracts` and reused by tests and the benchmark runner.
