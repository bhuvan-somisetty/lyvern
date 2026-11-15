# PRODUCT_SPEC

Status: draft v0.1 for owner approval. Product name: Lyvern (chosen 2026-11-16).

## 1. What we are building
A GitHub App plus web dashboard that reviews pull requests with a layered pipeline: structural code understanding, established static-analysis tools, small evaluated ML components, and an LLM used for reasoning and explanation. It publishes evidence-backed, line-level feedback on the PR and records every review so quality can be measured over time.

It assists human reviewers. It never merges, approves, requests changes, or pushes code.

## 2. Why it matters
- Reviewers spend time on mechanical issues and miss cross-file regressions and security problems.
- Existing AI review tools are widely perceived as noisy. False positives destroy trust, so our central promise is precision with visible evidence, plus a way to measure that precision.
- Teams have no objective view of review quality or PR risk over time.

## 3. Users
Primary: individual developers, open-source contributors and maintainers, small engineering teams, startups. Later: organizations with many repositories, security and quality teams. The data model is multi-tenant from day one (organization -> repositories); the first release can run single-tenant.

## 4. Finding model (core contract)
Every finding has: `id`, `category` (correctness, security, performance, maintainability, reliability, testing, documentation), `severity` (critical, high, medium, low, info), `confidence` (0-1, separate from severity), `origin` (`static_analysis` | `ml_prediction` | `llm_observation` | `human_confirmed`), `detection_source` (tool/rule/model id and version), `file_path`, `line_start`, `line_end`, `description`, `evidence` (code excerpt and/or rule trace, mandatory), `explanation`, `remediation`, `status` (open, resolved, dismissed, confirmed), timestamps.

Rules: no finding without evidence; an LLM observation is never labelled "verified vulnerability"; severity is derived from impact, exploitability and scope, not from model confidence.

## 5. Modules (A-J) and v1 scope
| Module | v1 (MVP) | Later |
|---|---|---|
| A GitHub integration | App install, signed webhooks, PR opened/synchronize/reopened/closed, diff + files, inline review comments + summary, dedup, retries, audit log | Check runs, commands via comments, GHES |
| B Diff intelligence | Unified diff parser, changed-line maps, rename/binary/large-file handling, token-aware context | Smarter related-file ranking |
| C Code understanding | Python (stdlib `ast` + tree-sitter), JS, TS via tree-sitter adapters; Go after that | More languages via adapter interface |
| D Static analysis | Semgrep, Ruff, ESLint, secret scan, dependency audit | CodeQL-like depth, custom rules |
| E ML | Evaluated baselines: finding classifier, similarity retrieval, explainable rule-based risk | Supervised risk model only if a real labeled set exists |
| F AI review | Provider-neutral client, structured JSON, schema validation, budgets and cost tracking | Fix-suggestion validation, multi-model routing |
| G Orchestration | Pipeline with normalize, dedupe, rank, validate-locations, publish, persist | Repo-specific guideline injection |
| H Risk engine | Explainable PR risk score with factor breakdown | Learned weights once data exists |
| I Dashboard | Overview, repos, PR history, review detail, findings, settings, empty states | ML evaluation and cost pages fully populated |
| J History/analytics | Search, filters, resolve/dismiss, export | Feedback-driven learning (carefully) |

## 6. Non-goals (v1)
Auto-merge or auto-approve; autonomous commits; running PR code; replacing formatters/linters for style; GitLab/Bitbucket; on-prem enterprise packaging.

## 7. Differentiation (prioritized by feasibility x measurable value)
1. Cross-file, dependency-aware review (callers/callees of changed symbols in Python/TS). High value, feasible.
2. Explainable PR risk with a factor breakdown. Feasible as a rule baseline immediately.
3. Measurable false-positive reduction: every finding is feedback-able and the dashboard reports precision with sample sizes. High value, feasible.
4. Historical defect-pattern retrieval via embeddings (needs accumulated data; benchmark first).
5. Repository-specific guidelines file (cheap, high value).
6. Regression impact analysis (builds on 1).
7. Later: learning from human feedback after quality-checking labels.

## 8. Success criteria
Per `ROADMAP.md` acceptance criteria. At product level: secure App install works end to end; reviews appear on real PRs with valid inline locations; measured precision on a documented benchmark, compared fairly against baseline tools (Semgrep alone, Ruff alone, an LLM-only baseline); dashboard shows only real data.

## 9. UX direction
Dark-first, graphite/charcoal surfaces, electric crimson accent, warm neutral text, strong type, restrained gradients, purposeful motion only, responsive. Clear empty states. Accessible (contrast, focus, `aria-live` for status, `prefers-reduced-motion`). Visual identity and logo wait for the final name.
