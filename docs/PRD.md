# Lyvern: Product Requirements Document (PRD)

Version 1.0, 2026-11-16. Owner: Bhuvan Somisetty. Status labels used throughout:
**BUILT** = implemented and verified by tests in this repository; **DESIGNED** = specified in docs, not implemented; **PLANNED** = intended, not yet designed in detail.

Read this together with `PROJECT_HANDBOOK.md` (the A-to-Z overview) and `TRD.md` (technical requirements).

---

## 1. Summary
Lyvern is an AI-assisted pull request review platform for GitHub. When a developer opens or updates a pull request, Lyvern analyses the change, runs deterministic security and quality tools, applies evaluated ML models and a language model, and posts evidence-backed review feedback directly on the PR: inline comments on the exact changed lines, general comments, a summary, and (when the repository allows it) a REQUEST_CHANGES or APPROVE review. A web dashboard shows review history, findings, risk and the measured quality of the reviewer itself.

It assists human reviewers. It prioritises being right over being loud.

## 2. Problem
- Human reviewers are slow, inconsistent, and miss cross-file effects and security issues, especially on large PRs.
- Existing AI reviewers are often noisy: many low-value or wrong comments erode trust, and teams stop reading them.
- Teams rarely know how good their automated reviews actually are: there is usually no measured precision, no false-positive tracking.
- Static analysers find real bugs but give no context about "why this matters in this PR" and cannot reason about intent.

## 3. Target users and personas
| Persona | Need | How Lyvern helps |
|---|---|---|
| Individual developer / student | Quick second pair of eyes before asking a human | Instant inline feedback on their own PR |
| Open-source maintainer | Triage many PRs, spot security issues in contributions | Risk score, blocking findings, consistent first-pass review |
| Small team / startup | No dedicated reviewer or security person | Automated first review + policy-driven request-changes |
| Tech lead / security engineer | Enforce standards, see trends | Repository rules, dashboards, audit history |

## 4. Goals
1. **Precision first:** every published finding has supporting evidence and a valid location. (Mechanism BUILT; measured precision PLANNED, see section 9.)
2. **Correct placement:** inline comments only on lines the PR added. (BUILT, property-tested.)
3. **Defensible decisions:** a transparent policy turns findings into COMMENT / REQUEST_CHANGES / APPROVE, with the reasons shown. (BUILT.)
4. **Honest provenance:** deterministic findings, ML predictions, AI observations and human confirmations stay distinguishable everywhere. (BUILT in the data model and rendering.)
5. **Measurable quality:** a benchmark and feedback loop that produce real precision/recall numbers. (PLANNED, harness design in `ML_DESIGN.md`.)
6. **Safe by design:** least privilege, untrusted-input handling, no execution of PR code, no secrets to an LLM. (DESIGNED in `SECURITY.md`; parts enforced in code.)

## 5. Non-goals (first releases)
Auto-merging; pushing commits; running the PR's code or tests; replacing formatters/linters for style nits; GitLab/Bitbucket; on-premise packaging; claiming superiority over other tools without a fair benchmark.

## 6. User stories and acceptance criteria
| # | Story | Acceptance criteria | Status |
|---|---|---|---|
| U1 | As a developer I want a review to start automatically when I open or update a PR | A signed GitHub webhook creates exactly one review run per PR head commit; duplicates ignored | DESIGNED |
| U2 | I want comments on the exact lines that caused the concern | Inline comments are posted only on lines the PR added; never on invalid locations | BUILT (logic); GitHub posting PLANNED |
| U3 | I want to know if something blocks the merge | REQUEST_CHANGES only for evidence-backed, confident, PR-introduced critical/high findings | BUILT (logic) |
| U4 | I want repo-wide concerns (missing tests, breaking change) as general comments | Findings with no valid inline anchor become general notes in the summary | BUILT |
| U5 | I want a summary with real numbers | Counts in the summary equal the counts of reported findings | BUILT |
| U6 | As a maintainer I want approval only when it is really safe | APPROVE requires opt-in, a fully successful run, no serious findings, low risk; otherwise COMMENT | BUILT (logic) |
| U7 | I want to dismiss a wrong finding and have the system learn carefully | Feedback is stored with context; not used as training labels until reviewed | DESIGNED |
| U8 | I want to see risk and why | Explainable risk score with factor breakdown | DESIGNED |
| U9 | I want to define repository rules | Repo-level policy/guidelines file affects review | DESIGNED (policy object BUILT) |
| U10 | As a security engineer I want secrets and tokens never leaked | Secret redaction before any LLM call; no tokens in logs | PARTIAL: log scrubbing BUILT; LLM redaction PLANNED |

## 7. Feature list with status
| Area | Feature | Priority | Status |
|---|---|---|---|
| GitHub | GitHub App install, signed webhooks, delivery dedup | P0 | **BUILT**, verified end to end in the sandbox repository |
| GitHub | Fetch PR, files, patches; post inline/general/summary reviews; dismiss own stale changes-requested review | P0 | **BUILT**, verified in the sandbox repository (inline comments on exact lines, REQUEST_CHANGES, COMMENT, dismissal); APPROVE path built but not yet exercised on GitHub |
| Diff | Unified diff parser with exact GitHub line mapping | P0 | **BUILT** |
| Review logic | Finding model with enforced invariants | P0 | **BUILT** |
| Review logic | Dedup and cross-source corroboration, ranking | P0 | **BUILT** |
| Review logic | Placement (inline/general/dropped) | P0 | **BUILT** |
| Review logic | Decision engine (COMMENT / REQUEST_CHANGES / gated APPROVE) | P0 | **BUILT** |
| Review logic | Review text rendering (no emojis, provenance labels) | P0 | **BUILT** |
| Analysis | Semgrep, Ruff, ESLint, secret scan, dependency audit adapters | P0 | PLANNED |
| Analysis | Code understanding (Python `ast`, tree-sitter: Python/JS/TS/Go) | P1 | PLANNED |
| ML | Finding classifier, semantic similarity (pgvector), explainable PR risk | P1 | DESIGNED |
| LLM | Provider-neutral client, schema-validated output, budgets, injection defences | P1 | DESIGNED |
| Platform | FastAPI service, Celery worker, Postgres + pgvector, Redis, Docker Compose, CI | P0 | **BUILT** (foundation) |
| Dashboard | Next.js dashboard shell | P1 | **BUILT** (empty-state shell only) |
| Dashboard | Repos, PR history, findings, analytics, settings | P1 | PLANNED |
| Quality | Benchmark harness, feedback loop, false-positive tracking | P0 | PLANNED |
| Reviewer mode | CLI that takes any PR URL, runs the same engine, and prints a DRAFT review for a human reviewer to read and post themselves; never posts on its own | P1 | **BUILT (first version)**: read-only GitHub client, Python analysis via Ruff, diff parsing, placement, verdict proposal; JS/TS/Go analysis not yet (those files are listed as not analysed). Needed because a GitHub App can only be installed by an owner/admin of the repository's account, so a contributor cannot use the App on other people's projects |

## 8. User experience
**Installation (once per account/repo):** open the Lyvern GitHub App page, click Install, choose repositories, accept the listed permissions. *(PLANNED: App not yet registered.)*

**Daily use:** nothing to run. Developer opens/updates a PR; within minutes Lyvern posts a review. The developer reads inline comments, fixes or dismisses them, pushes again; a new review runs for the new commit.

**Dashboard:** sign in with GitHub; see connected repos, PR history, per-PR review with findings, evidence, severity, confidence, source (static/ML/AI), risk; mark findings useful / false positive; view quality analytics. Only real data is shown; empty states otherwise.

**Tone of comments:** concise, specific, no emojis, states why it matters and a practical fix; AI observations are labelled as not independently verified.

## 9. Success metrics
No target is a result. Targets are goals to be measured on a documented benchmark; numbers will be published only when measured.
- Precision of published findings (share confirmed useful/true) on the benchmark, per source type.
- False-positive rate per PR; dismissal rate from real use.
- Blocking-finding precision (the most important number: wrongly blocking a PR is costly).
- Review latency (time from webhook to published review) and cost per PR.
- Coverage: share of changed files actually analysed (unsupported languages are reported honestly).

## 10. Release plan
| Release | Contents | Gate |
|---|---|---|
| R0 Foundation | Repo, CI, review logic, diff parser | DONE (this repository) |
| R1 Review MVP | GitHub App + Python static analysis + inline comments + summary | End-to-end on a real test PR; zero invalid inline locations |
| R2 Intelligence | Code understanding, LLM layer, risk score | Benchmark run published |
| R3 ML + Feedback | Classifier, similarity, feedback loop, analytics | Measured metrics with sample sizes |
| R4 Product | Dashboard, repo rules, multi-repo | Real users on private beta |

## 11. Risks and mitigations
| Risk | Mitigation |
|---|---|
| False positives destroy trust | Evidence required, corroboration for blocking, placement rules, measured precision |
| Prompt injection from PR content | Untrusted-data delimiting, schema-validated output, no tools for the model, injection test corpus |
| Bot approves something unsafe | Approval off by default; strict gate; branch protection stays authoritative |
| GitHub may not honour an App's approval | Verified empirically in the publishing milestone; reported clearly; never faked as a comment |
| LLM cost/latency | Budgets, caching, deterministic tools first |
| Small benchmark / weak labels | Document sizes and limits; never overclaim |
| Name/trademark | Trademark search still open for "Lyvern" |

## 12. Open questions
GitHub App registration (owner action); LLM provider and spend cap; hosting target; whether to ship the local CLI early as a demo path; trademark check for the name.
