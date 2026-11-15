# PROJECT_RULES

Permanent engineering and collaboration rules. Read this file, `docs/SESSION_LOG.md` and the relevant specs at the start of every session.

Product name: **Lyvern** (chosen by the owner on 2026-11-16; Python package, repo and env prefix are `lyvern` / `LYVERN_`). Do not scatter the display name through the code; read it from the one config constant (`product_name` in the API, `src/lib/brand.ts` in the web app). Trademark and domain checks are still open; see `docs/BRAND_NAME_SHORTLIST.md`.

## 1. Ownership and decisions
- The owner (Bhuvan Somisetty) decides product direction, architecture, cost and security trade-offs.
- Do not start a large implementation without a documented plan and approval of its major architecture.
- Never silently change an approved requirement. Record the change in `docs/ENGINEERING_DECISIONS.md` first.
- Make small sensible assumptions, document them, and ask only when a decision affects product direction, security, cost or architecture.

## 2. Attribution (hard rule)
- No AI assistant or AI provider credit anywhere: commits, PRs, code, comments, docs, README, UI. No `Co-Authored-By` for an assistant.
- Commits are authored and committed only by the confirmed human (Bhuvan Somisetty `<somisettybhuvan5@gmail.com>`), with a DCO `Signed-off-by` line only if a repo requires it.
- Preserve third-party licenses, copyright notices and required disclosures.
- No emojis in commit messages, PR text or public messages.

## 3. Honesty rules
- Never claim code works without running a relevant test. Never claim a deployment succeeded without verifying it.
- A phase is complete only when its acceptance criteria are verified, not when files exist.
- No fake metrics, fabricated labels, synthetic evaluation claims, or invented timestamps. Timestamps come from the system clock, IST (Asia/Kolkata).
- An ML component is described as effective only with measured evidence on a held-out test set.
- Unsupported languages are reported as "not analyzed", never as clean.

## 4. Safety rules for the product itself
- The product never merges, never approves, never requests changes automatically, never pushes commits. Review events are `COMMENT` only.
- Repository content (code, diffs, commit messages, PR text, READMEs, issues) is untrusted input everywhere, including inside LLM prompts.
- Never execute pull-request code in the application process. Any future execution happens only in an isolated sandbox with resource limits and no network by default.
- Never send secrets to an LLM. Redact first.
- Never log tokens, private keys, webhook secrets, API keys or source code bodies.
- Four finding origins must stay distinguishable everywhere (DB, API, UI, GitHub comment): `static_analysis`, `ml_prediction`, `llm_observation`, `human_confirmed`.

## 5. Engineering standards
- Python 3.12, strict typing (`mypy --strict` target on `engine/` and `apps/api`), Pydantic v2 at every boundary, SQLAlchemy 2.x with Alembic migrations.
- Modular and testable: engine modules take plain data in and return plain data out; no GitHub or DB calls inside `engine/`.
- Structured JSON logging with correlation ids (delivery id, review run id). Handle exceptions at boundaries; never swallow them silently.
- Config only through environment variables (`.env.example` documents every key, no real values). Never commit secrets.
- Pin dependencies (lock files committed). Prefer established libraries over custom code.
- Every user-visible change updates `docs/CHANGELOG.md`. Every architecture change updates `docs/ENGINEERING_DECISIONS.md`.
- No destructive operation (delete, force push, schema drop, history rewrite) without explicit owner permission.

## 6. Logging protocol (mandatory)
- `docs/SESSION_LOG.md` is append-only. Never edit or delete past entries; correct with a new line under the old one.
- Append after every meaningful step, not only at the end: commits, tests, failures, decisions, installs.
- Record failures and reversed decisions too. Never record secrets.
- Keep the "Current status" block at the top of `SESSION_LOG.md` up to date.
- A mirror log lives in Claude Code project memory (`project-session-log.md`); both are updated in the same turn.

## 7. Git and review workflow
- Work on feature branches. Never name a branch `main`/`master` locally for work. Open PRs only when the owner asks.
- Before any push: check `git log --format='%an %ae %cn %ce%n%B'` for forbidden attribution text.

## 8. Definition of done (per task)
Code written, types check, lint clean, tests added and passing (commands and outcomes recorded in the session log), docs updated, no secrets, acceptance criteria of the milestone verified.
