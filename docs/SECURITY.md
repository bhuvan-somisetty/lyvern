# SECURITY

Status: threat model v0.1 (design). No controls are implemented yet.

## 1. Assets
GitHub App private key, webhook secret, installation tokens, LLM API keys, users' source code and diffs (private repos), findings (may describe unpatched vulnerabilities), user sessions, tenant isolation.

## 2. Trust boundaries and untrusted input
Untrusted: webhook payloads (until signature verified), PR title/body, commit messages, branch names, file names, file contents, diffs, comments, README/docs, dependency manifests, anything returned by static analyzers about those files. Semi-trusted: GitHub API responses (still validated by schema). Trusted: our own code and config.

## 3. Threats and controls
| Threat | Control |
|---|---|
| Forged webhooks | HMAC-SHA256 over the raw body, constant-time compare, reject before parsing; secret from env; replay limited by delivery-id dedup |
| Duplicate/replayed events | Unique `X-GitHub-Delivery` in `webhook_deliveries`; unique run key `(repo, pr, head_sha, pipeline_version)` |
| Private key / token leak | Key from secret store or env, never logged, never in DB; installation tokens kept in memory/short-lived cache, scoped to one repo; log scrubbing filter tested |
| Excess GitHub permissions | Minimum set (see section 4); permission audit in tests; additions need an ENGINEERING_DECISIONS entry |
| Prompt injection via repo content | Repo text always inside delimited "untrusted data" blocks; system rules state that embedded instructions are ignored; the model has no tools and no network; output only accepted as schema-validated JSON; model cannot choose actions (publishing, labels, approvals are code-controlled); injection test corpus in `tests/security/` |
| Secrets sent to an LLM | Secret scanner runs first; detected secrets are replaced with `[REDACTED:type]` in any prompt; secret findings report type/location only, never the value |
| Executing hostile PR code | Never executed in the API/worker app process. Analyzers parse text only; no install/build/test. Any future execution: separate sandbox (no network, no secrets, CPU/mem/time/disk limits, read-only mount) |
| Malicious files (zip bombs, huge diffs, pathological regex/AST depth) | Per-file and per-PR size caps, parse timeouts, tree depth limits, skip binaries/generated/vendored; analyzer subprocess timeouts and memory limits |
| ReDoS via user-supplied patterns | Do not accept user regex in v1; if added later, use a linear-time engine or timeouts (PR-Agent uses a per-pattern time budget for this reason) |
| Path traversal when materializing files | Normalize and verify every path stays under the work dir; reject `..`, absolute paths, symlinks |
| Cross-tenant data access | `organization_id` on every tenant row, service-layer authorization checks, Postgres RLS as defense in depth, tests that try cross-tenant reads |
| Auth/session attacks | GitHub OAuth through the App's user-to-server flow, httpOnly + Secure + SameSite cookies, CSRF protection for state-changing routes, short sessions, org membership verified against GitHub |
| API abuse | Rate limiting per user/IP/installation, request size limits, pagination caps |
| Information leakage in errors | Generic error bodies, correlation id only; details in server logs without secrets or code bodies |
| Dependency vulnerabilities | Lockfiles, `pip-audit`/`npm audit` and Dependabot in CI, Semgrep on our own repo |
| Data retention | Source/diff content kept only for the configured TTL (default proposal: 30 days); findings keep short evidence snippets; repo disconnect and org deletion purge data; audit log records deletions |

## 4. GitHub App permissions (proposal)
- Metadata: read (mandatory).
- Pull requests: read and write (read PR/files; write review comments).
- Contents: read (fetch file blobs at base/head for context).
- Checks: write — NOT in v1; add only if we ship check runs.
- Issues, Actions, Administration, Secrets, Workflows: none.
- Events: `pull_request`, `installation`, `installation_repositories`; later `pull_request_review_comment` / `pull_request_review_thread` for feedback signals.
- The publisher API accepts only `event="COMMENT"`; `APPROVE` and `REQUEST_CHANGES` do not exist in our client type, so they cannot be sent by mistake.

## 5. Privacy
- External LLM use is per-installation opt-in with a documented provider and data-handling statement; default off until the owner enables it. Embeddings also leave the machine if a hosted embedding API is used; local models are the default candidate.
- No code is uploaded to any third party without that consent flag.
- Users can disconnect a repository (stops processing, schedules purge) and delete their account data.
- Telemetry: none by default.

## 6. Audit logging
Append-only `audit_logs`: installation added/removed, repo connected/disconnected, settings changed, finding status changed by a human, data export, data deletion, auth events. Includes actor, time, target, request id. No secrets or code bodies.

## 7. Security testing plan
Webhook signature tests (valid, invalid, missing, tampered body), replay/dedup tests, prompt-injection corpus (instructions in code comments, commit messages, README, filenames), path traversal tests, cross-tenant tests, log-scrubbing tests, oversize/malformed diff fuzzing, dependency scan in CI.

## 8. Open items
Secret store for production, key rotation procedure, incident response contact, vulnerability disclosure policy (`SECURITY.md` at repo root when public), and verifying licensing terms for Semgrep registry rules before any commercial use.
