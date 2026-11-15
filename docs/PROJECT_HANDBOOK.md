# Lyvern: Project Handbook (everything, A to Z)

Version 1.0, 2026-11-16. This is the one document to read first. Deeper detail lives in `PRD.md` (what and why), `TRD.md` (how), and the specialist docs listed in section 14.

Status labels: **BUILT** = implemented and verified by tests in this repo; **DESIGNED** = specified, not built; **PLANNED** = intended.

---

## 1. What is Lyvern, in plain words
Lyvern is a **GitHub App** that reviews pull requests (PRs) automatically. A developer opens a PR; Lyvern reads the change, runs security and quality tools, applies ML models and a language model, and writes a review **on the PR itself**: comments on the exact changed lines, a summary, and, if the repository allows it, "request changes" or "approve". A web **dashboard** shows history, findings, risk, and how accurate the reviewer has been.

It is not a chatbot wrapped around a diff. The language model is one input among several, and nothing it says can block a merge unless something independent backs it up.

## 2. How do people use it? (extension? CLI? what do I do?)
**It is not a browser extension.** It is a GitHub App plus a website. Planned usage:

1. **Install once.** On GitHub, open the Lyvern App page, click *Install*, pick the repositories, accept the permissions (read code and PRs, write review comments). *(PLANNED: the App is not registered yet.)*
2. **Work normally.** Open or update a pull request as you always do. There is nothing to run.
3. **Get the review.** Within minutes Lyvern posts a review on the PR:
   - inline comments on specific added lines ("this query is built from user input", "result may be None here"),
   - general comments for PR-wide points (missing tests, breaking change),
   - a summary with real counts, what was and was not analysed, and the decision.
4. **Respond.** Fix the issue and push (a new review runs for the new commit), or mark a finding *useful* / *false positive* in the dashboard.
5. **Dashboard (optional).** Sign in with GitHub to see PR history, findings by severity/category, risk, and quality analytics for the reviewer.
6. **Repository rules (optional).** Choose whether the bot may request changes or approve, which severities block, risk limits.

**Who uses it:** individual developers and students (a second pair of eyes), open-source maintainers (first-pass triage and security screening), small teams without a dedicated reviewer, tech leads and security engineers (policy and trends).

**A possible extra (PLANNED):** a small local command that reviews a git diff on your machine using the same engine. It would let anyone try Lyvern without installing the App, and makes a good live demo.

### Example of what a developer sees
This is **real output of the review engine** (`render_inline` and `render_summary`), run on a small sample patch. The finding itself was supplied by hand for this example, because the analysis stages that will produce findings automatically are not built yet. The comment location (line 11 of `app.py`) was chosen by the real placement code from the real parsed diff.

Inline comment on `app.py` line 11:

> **HIGH | security** - Shell injection
>
> subprocess is called with shell=True and a caller-controlled command string.
>
> Why it matters: Arbitrary command execution if cmd contains user input.
>
> Suggested fix: Pass an argument list and drop shell=True.
>
> Evidence:
> ```
> subprocess.call(cmd, shell=True)
> ```
>
> Source: Static analysis (semgrep:py-shell-true). Confidence: 90%. This finding is blocking.
>
> <!-- lyvern:fp=ec7c014560f6d241bac0 -->

Review summary:

> **Automated pull request review (Lyvern)**
>
> This review was generated automatically. It does not replace human review, and branch protection rules still apply.
>
> Result: Changes requested.
>
> Files: 1 changed, 1 analyzed, 0 not analyzed.
>
> Findings: 1 reported (high: 1); 1 inline, 0 general.
> By category: security: 1.
>
> Blocking findings:
> - `app.py:11` Shell injection
>
> Recommendation: please address the blocking findings and re-run the relevant tests before merging.

## 3. What exists today (honest status)
| Part | Status |
|---|---|
| Repo, CI on GitHub (green), Docker stack, API health, worker, DB migrations, dashboard shell | **BUILT** |
| Review engine: finding model, diff parser, dedup/ranking, placement, decision engine, rendering | **BUILT**, 75 unit tests + property tests against real `git diff` |
| GitHub App connection (webhooks, fetch PR, post reviews) | PLANNED, next milestone |
| Static analysis (Semgrep, Ruff, ESLint, secrets, dependencies) | PLANNED |
| Code understanding (tree-sitter / `ast`, cross-file) | PLANNED |
| ML models (classifier, similarity, risk) and benchmark | DESIGNED / PLANNED |
| LLM layer | DESIGNED |
| Dashboard pages and analytics | PLANNED |

**Today it cannot review a real PR end to end.** What exists is the foundation and the part that decides whether a comment is valid and what the review verdict is.

## 4. How a review works (the pipeline)
1. GitHub sends a signed webhook when a PR is opened/updated. *(DESIGNED)*
2. Lyvern fetches the PR and its diff. *(PLANNED)*
3. The diff is parsed so every changed line has an exact location. **(BUILT)**
4. The code is understood structurally: functions, imports, callers. *(PLANNED)*
5. Established tools look for bugs and vulnerabilities; each finding must carry evidence. *(PLANNED)*
6. ML models classify findings, find similar past issues, estimate risk. *(DESIGNED)*
7. A language model reasons about what tools cannot (logic, cross-file effects). *(DESIGNED)*
8. Findings are merged, de-duplicated, ranked. **(BUILT)**
9. Each finding gets a place: inline, general, or dropped. **(BUILT)**
10. The decision engine picks COMMENT / REQUEST_CHANGES / APPROVE with reasons. **(BUILT)**
11. The review text is rendered and posted; everything is stored. *(rendering BUILT; posting PLANNED)*

## 5. What makes Lyvern special (design principles)
1. **Evidence or silence.** A finding without evidence cannot exist: the data type forbids it.
2. **Provenance is never blurred.** Every finding is labelled static analysis, ML prediction, AI observation, or human-confirmed, in the database, API and the comment text. An AI observation is never presented as a verified defect.
3. **AI cannot block alone.** An uncorroborated AI or ML finding can never be blocking. This is enforced in the type and tested with random inputs.
4. **Comments land where they should.** Inline comments only on lines the PR added, never on unchanged or invented locations. The diff parser was verified against real `git diff` output on hundreds of generated cases.
5. **Approval is a safety decision, not a feature toggle.** Off by default; needs a fully successful run, no serious findings, low risk; otherwise it says why it did not approve. A failed run is reported as failed, never as success.
6. **Pre-existing problems are not blamed on the PR.** They are dropped or reported separately.
7. **Measured, not claimed.** A benchmark and feedback loop are part of the plan so accuracy is a number with a sample size.
8. **Built to be tested.** The review logic is pure code with no network or database, which is why it can be tested exhaustively with property-based tests and mutation checks.
9. **Honest about limits.** Unsupported languages and unanalysed files are reported, not silently skipped.

## 6. Why these technologies (and not the alternatives)
See `TRD.md` section 2 for the table. Highlights:
- **GitHub App instead of an extension or Action:** one install, webhooks, scoped short-lived tokens, central history, a distinct bot identity.
- **Hybrid (tools + ML + LLM) instead of LLM-only:** tools give verifiable evidence; ML gives measurable, explainable signals; the LLM adds reasoning where the others cannot. LLM-only reviewers are the main source of noisy comments.
- **Python/FastAPI:** the analysis and ML ecosystem lives in Python.
- **Postgres + pgvector:** one datastore until scale proves otherwise.
- **Property tests against real git:** the strongest available proof that line numbers are right.

## 7. How it compares to similar tools
Based on the public descriptions and code seen during research (see `REFERENCE_RESEARCH.md`); capabilities of other products change, so verify before quoting. **Lyvern is early and less mature than all of these. The differences below are design goals, not proven advantages. No fair benchmark has been run yet, so no superiority is claimed.**

| Tool | What it is (as researched) | How Lyvern aims to differ |
|---|---|---|
| PR-Agent (open source, MIT; Qodo's engine) | Open-source PR review/describe/improve tool; reads the diff, token-aware context, prompts the model, supports many git hosts | Typed evidence-required findings with provenance; database-enforced dedup; ML components with published evaluation; gated approval with reasons; dashboard analytics |
| Qodo Merge | Hosted product around PR-Agent; `/review` commands, configurable | Same differences; plus measured precision as a first-class feature |
| CodeRabbit | Widely used hosted AI reviewer for GitHub (per third-party listings) | Transparency of decision logic; deterministic-first; open design |
| Greptile | AI reviewer emphasising whole-codebase understanding; funded company | Comparable goal (cross-file context) via tree-sitter call graph, but with evidence gating and ML evaluation |
| Kusari Inspector | Security-focused PR review with SAST, secret and dependency scanning | Broader scope (bugs, performance, quality) with the same evidence discipline |
| Semgrep / Ruff / ESLint (used inside Lyvern) | Deterministic analysers | Lyvern consumes them and adds context, ranking, placement and decisions |
| SonarQube / Codacy / DeepSource style platforms | Rule-based quality dashboards | Review happens as PR comments with explanations and fixes; models add reasoning |
| Plain "send the diff to an LLM" scripts | Quick but noisy | Structural understanding, evidence gates, no AI-only blocking |

## 8. Roadmap
R1 Review MVP (GitHub App + Python analysis + inline comments + summary) → R2 intelligence (code understanding, LLM, risk) → R3 ML and feedback loop with a published benchmark → R4 dashboard and multi-repo. Details and acceptance criteria: `ROADMAP.md`, `PRD.md` section 10.

## 9. How to run and verify it today
```bash
git clone https://github.com/bhuvan-somisetty/lyvern   # private repo, owner access
cp .env.example .env
docker compose up -d --build            # db :5433, redis :6380, api :8000, worker
curl http://localhost:8000/readyz       # {"status":"ready", ...}
uv sync --all-packages
uv run ruff check . && uv run mypy && uv run pytest tests
cd apps/web && pnpm install && pnpm dev
```
Where the code is: `packages/lyvern/src/lyvern/engine` (review logic), `apps/api`, `apps/worker`, `apps/web`, `tests/`.

## 10. What you can safely say on a resume today
True and verifiable now:
- Built the core of a GitHub PR review platform in Python: a diff parser that maps changed lines to GitHub review positions, verified against real `git diff` output with property-based tests.
- Designed an evidence-gated review decision engine (comment / request changes / policy-gated approve) with safety properties verified by property tests and mutation checks.
- Set up a typed, tested, containerised monorepo (FastAPI, Celery, PostgreSQL + pgvector, Redis, Next.js) with CI on GitHub Actions.

**Do not claim** an accuracy percentage, a trained model, static-analysis integration, or an LLM reviewer until those exist and are measured. The plan is to produce real benchmark numbers (precision/recall against baseline tools) so the resume line can later carry a measured result.

## 11. Security stance (summary)
Treat all repository content as untrusted; least-privilege GitHub permissions; verify webhook signatures; never run PR code in the app; never send secrets to an LLM; tenant isolation; audit logs; retention limits. Details: `SECURITY.md`.

## 12. FAQ
**Does it replace human review?** No. Every review says it is automated.
**Will it merge my PR?** Never. It cannot merge or push.
**Will it approve my PR?** Only if the repository opts in and every safety condition holds; GitHub rules still apply.
**What about languages it does not understand?** Files in unsupported languages are listed as "not analysed", not marked clean.
**Is my code sent to an AI provider?** Only with an explicit per-installation opt-in; secrets are redacted first. *(DESIGNED)*
**Why is the product called Lyvern?** Chosen by the owner on 2026-11-16 after availability checks; trademark search is still open.

## 13. Glossary (A to Z)
- **Approve / Request changes / Comment:** the three GitHub review events.
- **Blocking finding:** a finding that may justify request-changes; needs trusted evidence and confidence.
- **Branch protection:** GitHub rules that stay authoritative over the bot.
- **Confidence:** how sure the detector is; separate from severity.
- **Corroboration:** an independent trusted source reporting the same issue.
- **Dedup:** collapsing repeated reports of one issue.
- **Diff / hunk:** the changed regions of a file in a pull request.
- **Evidence:** the code or rule trace that supports a finding; mandatory.
- **Fingerprint:** a stable identity of a finding that survives moved lines.
- **GitHub App:** an installable integration with its own identity and scoped permissions.
- **Hunk header (`@@`):** the line that gives the line ranges of a hunk.
- **Inline comment:** a comment attached to a specific line.
- **LLM observation:** a finding from a language model; never treated as verified on its own.
- **Origin:** static analysis, ML prediction, LLM observation, or human-confirmed.
- **pgvector:** Postgres extension for similarity search on embeddings.
- **Position / line + side:** how GitHub identifies where an inline comment goes.
- **Precision / recall:** share of reported findings that are right / share of real issues found.
- **Property-based test:** a test over many generated inputs checking a rule always holds.
- **Provenance:** where a finding came from.
- **Risk score:** an explainable estimate of how risky a PR is.
- **Severity:** impact of a finding (critical to info).
- **Static analysis:** checking code without running it (Semgrep, Ruff, ESLint).
- **Superseded run:** a review for an older commit replaced by a newer one.
- **tree-sitter:** an error-tolerant parser used to understand code structure.
- **Untrusted input:** all repository content; never obeyed as instructions.
- **Webhook:** GitHub's HTTP call telling us a PR event happened.
- **Zero fabrication:** the project rule that no number, label or result is invented.

## 14. Document map
`PRD.md`, `TRD.md`, `PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `API_SPECIFICATION.md`, `ML_DESIGN.md`, `SECURITY.md`, `ROADMAP.md`, `ENGINEERING_DECISIONS.md`, `REFERENCE_RESEARCH.md`, `BRAND_NAME_SHORTLIST.md`, `SESSION_LOG.md` (full development history), `CHANGELOG.md`.
