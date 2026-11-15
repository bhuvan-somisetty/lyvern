# DATABASE_SCHEMA

Status: design v0.1. PostgreSQL 16+ with `pgvector`. SQLAlchemy 2.x models, Alembic migrations (none written yet). All ids are UUIDv7 or UUIDv4; all timestamps `timestamptz` in UTC.

## Tenancy rule
Every tenant-owned table has `organization_id` (FK, NOT NULL, indexed). Authorization is checked in the service layer; row-level security policies keyed on a per-request `app.current_org` setting are the defense-in-depth plan.

## Entities
**users**: id, github_user_id (unique), login, display_name, email (nullable), avatar_url, created_at, last_login_at.

**organizations**: id, github_account_id (unique), github_login, account_type (user|org), plan, retention_days (default 30), external_llm_enabled (default false), created_at, deleted_at.

**memberships**: id, organization_id, user_id, role (owner|admin|member), unique(organization_id, user_id).

**github_installations**: id, organization_id, github_installation_id (unique), repository_selection (all|selected), permissions (jsonb snapshot), suspended_at, installed_at, uninstalled_at. No tokens stored.

**repositories**: id, organization_id, installation_id, github_repo_id (unique), full_name, default_branch, private, language_stats (jsonb), status (active|disconnected), connected_at, disconnected_at, purge_after.

**repository_settings**: repository_id (PK), enabled_analyzers (jsonb), guidelines_text (nullable), ignore_globs (text[]), min_severity_to_comment, max_comments_per_review, draft_pr_policy.

**webhook_deliveries**: id, delivery_id (unique, from X-GitHub-Delivery), event, action, installation_id, repository_id (nullable), signature_valid (bool), received_at, processed_at, status (received|queued|processed|failed|ignored), error (text, no payload secrets), payload_sha256. Raw payload NOT stored beyond a short TTL (optional debug table with TTL).

**pull_requests**: id, organization_id, repository_id, github_pr_number, github_pr_id, title, author_login, base_ref, head_ref, state, draft, opened_at, closed_at, merged_at, last_head_sha; unique(repository_id, github_pr_number).

**review_runs**: id, organization_id, repository_id, pull_request_id, head_sha, base_sha, trigger_delivery_id, pipeline_version, status (queued|running|succeeded|partial|failed|superseded|cancelled), started_at, finished_at, step_timings (jsonb), limitations (jsonb: unparsed files, skipped files, unsupported languages), risk_score (numeric), risk_level, risk_factors (jsonb), github_review_id (nullable), error (text); unique(repository_id, pull_request_id, head_sha, pipeline_version).

**changed_files**: id, review_run_id, path, old_path, status (added|modified|removed|renamed), additions, deletions, language, analyzed (bool), skip_reason, patch_sha256. Patch text is held only under retention rules (see `diff_blobs`).

**diff_blobs**: id, review_run_id, changed_file_id, patch_text, expires_at. Purged by a retention job.

**symbols**: id, review_run_id, file_path, kind (function|class|method|module), qualified_name, line_start, line_end, changed (bool), content_hash. **symbol_edges**: from_symbol_id, to_symbol_id (or unresolved name), edge_type (calls|imports|inherits), resolved (bool).

**findings**: id, organization_id, repository_id, pull_request_id, review_run_id, fingerprint (stable hash for dedup and recurrence tracking), category, severity, confidence (0..1), origin (static_analysis|ml_prediction|llm_observation|human_confirmed), detection_source, rule_id, file_path, line_start, line_end, title, description, evidence (text, short excerpt), explanation, remediation, suggested_patch (nullable), status (open|resolved|dismissed|confirmed), published (bool), github_comment_id (nullable), created_at, updated_at.
Indexes: (organization_id, repository_id, status), (review_run_id), (fingerprint), (category, severity), GIN full-text on title+description.

**finding_feedback**: id, finding_id, user_id (nullable for GitHub-originated), source (dashboard|github_reaction|github_resolve), verdict (useful|not_useful|false_positive|fixed|wont_fix), reason (text), context (jsonb: later commits touched the line? same-author? etc.), created_at. Kept separate from labels; a curated `labeled_examples` set is built from it only after quality review.

**llm_calls**: id, review_run_id, provider, model, purpose, prompt_tokens, completion_tokens, cost_usd (numeric), latency_ms, status, schema_valid (bool), created_at. Prompt/response bodies are not stored by default.

**embeddings**: id, organization_id, owner_type (finding|symbol|pr), owner_id, model_id, dim, vector `vector(N)`, created_at. One table per distinct dimension if models differ; HNSW index with cosine ops, chosen after the benchmark.

**ml_models**: id, name, task (classifier|similarity|risk), version, artifact_uri, training_data_manifest (jsonb), metrics (jsonb), created_at, active (bool). **ml_evaluations**: id, model_id, dataset_name, split, metrics (jsonb: precision, recall, f1, confusion matrix, calibration), n_examples, created_at.

**audit_logs**: id, organization_id, actor_user_id (nullable), actor_type (user|system|github), action, target_type, target_id, request_id, metadata (jsonb, no secrets), created_at. Append-only (no UPDATE/DELETE grants to the app role).

**api_sessions** (if server-side sessions): id, user_id, created_at, expires_at, ip_hash, user_agent_hash.

## Relationships (summary)
organization 1-n installations 1-n repositories 1-n pull_requests 1-n review_runs 1-n findings; findings 1-n finding_feedback; review_runs 1-n changed_files/symbols/llm_calls; users n-n organizations via memberships.

## Retention
A nightly job deletes `diff_blobs` past `expires_at` and any source excerpts beyond policy; disconnecting a repo sets `purge_after`; deleting an organization hard-deletes tenant rows after a grace period and logs it in `audit_logs`.

## Migration policy
Alembic only; every migration reviewed; no manual DDL; downgrade scripts for non-destructive changes; CI runs `alembic upgrade head` on an empty DB and compares models to the migrated schema.
