# ENGINEERING_DECISIONS

Append new decisions at the bottom. Reversed decisions stay in the file with a "Superseded by" note. Status values: Proposed (awaiting owner approval), Accepted, Superseded.

## ED-001 Temporary identifier and no hardcoded brand
Status: Proposed. Use `pr-intel` / package `printel`. Product name comes from one config constant once chosen. Reason: owner has not selected a name; avoids a repo-wide rename later.

## ED-002 Modular monolith plus separate worker, no microservices yet
Status: Proposed. `apps/api` and `apps/worker` share the `printel` Python package. Reason: one team, one deploy unit per role, easy local dev; extraction only on measured need.

## ED-003 Celery + Redis, with the database as source of truth
Status: Proposed. Reason: mature retries, ack-late semantics, scheduling for retention jobs. Alternatives: Arq (async-native, less tooling), RQ (simple, weaker retry story). Revisit if async I/O dominates.

## ED-004 Parse with `ast` (Python) and tree-sitter (all languages)
Status: Proposed. Reason: tree-sitter tolerates syntax errors and works across languages; `ast` gives exact Python semantics. Adapters behind one protocol; unsupported languages are reported as not analyzed.

## ED-005 Use existing analyzers, normalize their output
Status: Proposed. Semgrep, Ruff, ESLint, secret scanner, dependency audit. Do not reimplement rules. Evidence snippets are read by our code because Semgrep OSS output omits matched lines (verified locally). To verify before commercial use: Semgrep registry rule license terms.

## ED-006 Review events are COMMENT only
Status: Proposed. The GitHub client type cannot express APPROVE/REQUEST_CHANGES/merge. Reason: product rule "assist, never decide".

## ED-007 Four finding origins kept distinct end to end
Status: Proposed. `static_analysis`, `ml_prediction`, `llm_observation`, `human_confirmed` persist in DB, API, UI and comment text. Severity and confidence are separate fields.

## ED-008 pgvector in the primary Postgres
Status: Proposed. Reason: fewer moving parts. Revisit if vector scale or latency demands a dedicated store.

## ED-009 Risk engine v1 is rule-based and explainable, not a trained model
Status: Proposed. Reason: no defensible labeled dataset yet; a transparent baseline is honest and useful. Supervised model only after the label gate in ML_DESIGN.md.

## ED-010 LLM provider abstraction and opt-in external processing
Status: Proposed. `LLMProvider` protocol, structured output validated by JSON schema, redaction before any call, per-installation consent flag default off.

## ED-011 Generate the TypeScript client from OpenAPI
Status: Proposed. Replaces hand-maintained `packages/shared-types`. Reason: prevents contract drift.

## ED-012 Retention default 30 days for source/diff content
Status: Proposed (needs owner confirmation). Findings keep only short evidence snippets. Configurable per organization.

## ED-013 Repository layout refinement
Status: Proposed. See ARCHITECTURE.md section 4 (uv workspace, generated client, defer review-sdk, unit tests beside packages).

## Reference-driven notes (not decisions yet)
- PR-Agent (MIT) bounds user-supplied regex with a time budget and marks PR text as untrusted in prompts; we adopt the principles independently, no code copied.
- PR-Agent offers a webhook delivery de-duplication setting; we make dedup unconditional and database-enforced.

## Update 2026-11-16: acceptance and new decision
ED-001 to ED-013: Accepted by default on 2026-11-16 (owner chose the recommended defaults for the open questions Q1-Q8). Any can be reopened.

## ED-014 Repository lives outside OneDrive
Status: Accepted (owner choice, 2026-11-16). Path `C:\Users\BHUVAN\dev\pr-intel`. Reason: OneDrive would sync `.git`, `.venv`, `node_modules` and caches (slow, space use, corruption risk). The old OneDrive folder keeps the Phase 0 docs as a backup copy. The temporary name stays `pr-intel`; no remote is created before the brand is chosen.
