# REFERENCE_RESEARCH

Date studied: 2026-11-15 (IST). Method per source is stated honestly. We study practices only: no copied code, prompts, branding or designs. "Studied: code" means I cloned a shallow copy to a scratch folder and read files; "docs/search" means a web search summary, not a full read.

## 1. PR-Agent
- Repo: https://github.com/The-PR-Agent/pr-agent (MIT License, "Copyright (c) 2026 The PR Agent", read from `LICENSE`).
- Method: **studied: code** (cloned, read directory layout, `algo/`, `servers/`, `settings/`).
- Observations:
  - Layout: `agent/` (command routing), `commands/` (`pr_reviewer.py`, `pr_description.py`, `pr_code_suggestions.py`, ...), `git_providers/` (GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, Gerrit, CodeCommit, local), `servers/` (GitHub App, webhooks, polling, Lambda), `algo/` (diff and token logic), `settings/*.toml` (prompts and config).
  - Diff handling (`algo/pr_processing.py` ~1200 lines, `algo/git_patch_processing.py`): token-aware diff packing, extra context lines before/after hunks, hunk conversion to numbered lines, compressed diffs when over budget, multi-chunk processing, fallback model chain on failure, handling of deleted-only hunks, filtering of generated/ignored files (`ignore.toml`, `generated_code_ignore.toml`).
  - Deterministic checks (`algo/deterministic_risk.py`): sensitive-path globs and risky "change shapes" in diffs with no model call; custom regexes are length-limited and run under a per-search timeout and a per-review time budget (ReDoS defense).
  - `algo/structural_reach.py`: a deterministic Low/Moderate/High/Critical row computed from build-graph facts supplied in a JSON file; shows that a structural reach signal can be rule-based.
  - Webhooks (`servers/github_app.py`): signature verification via `x-hub-signature-256` (`verify_signature`), work done in a background task after responding, a configurable delivery-deduplication setting, installation id carried in context.
  - Prompts (`settings/pr_reviewer_prompts.toml`): PR title/description/commits/code explicitly marked as untrusted data that cannot change role, schema or instructions; earlier findings passed back as untrusted data to avoid restating them.
  - Findings (`algo/findings.py`): a frozen `Finding` dataclass with path, line range, body, label, existing/improved code, score and confidence.
- What we may implement independently: token-budgeted diff packing, extended hunk context, generated-file filters, deterministic sensitive-path checks, untrusted-data delimiting, finding dedup against earlier findings.
- What we deliberately do differently: evidence-mandatory typed findings with an origin field; dedup enforced by the database; Postgres-backed history and feedback analytics; tree-sitter based cross-file context; ML components with published evaluation; one provider (GitHub) first, no multi-forge sprawl.

## 2. Semgrep
- Repo: https://github.com/semgrep/semgrep. Method: **studied: tool behavior** (ran installed Semgrep 1.161.0 with a local rule on a scratch file); repository source not cloned (large).
- Observations: `--json` result keys: `version, results, errors, paths, time, engine_requested, skipped_rules, profiling_results`. Each result has `check_id`, `path`, `start/end {line, col, offset}`, and `extra {message, metadata, severity, fingerprint, lines, validation_state, engine_kind}`. In the OSS offline run, `extra.lines` and `extra.fingerprint` were the literal string `"requires login"`, so evidence must be read from the source file by our code. Custom rule YAML supports `metadata` (e.g. CWE) that we can map to categories. Semgrep needs `--metrics=off` and `--disable-version-check` for quiet CI use.
- To verify later: license terms of registry rules vs. the engine license for any commercial deployment; exact Windows support level (it ran here natively).
- Implement independently: adapter that runs Semgrep with our own rule packs and maps `check_id`, location, severity, CWE metadata into the finding model. Differently: we do not trust repo-provided configs.

## 3. Tree-sitter
- Repo: https://github.com/tree-sitter/tree-sitter. Method: **studied: README and layout** (cloned; read README, listed `lib/src`: `parser.c`, `query.c`, `tree.c`, `get_changed_ranges.c`, ...).
- Observations: parser generator and incremental parsing library producing a concrete syntax tree; documented goals: general, fast, robust to syntax errors, dependency-free C runtime; bindings (Rust, Wasm) and a CLI; a query language (`query.c`) enables pattern matching on trees; `get_changed_ranges` supports incremental diffing between trees.
- Not yet verified (needs install in M4): Python binding package names and wheel availability on Windows/Linux, grammar package versions for Python/JS/TS/Go.
- Implement independently: `LanguageAdapter` per language using queries to extract functions, classes, imports and call sites with exact line ranges.

## 4. CodeBERT family
- Repo: https://github.com/microsoft/CodeBERT. Method: **studied: README and layout** (cloned).
- Observations: the repo hosts CodeBERT (EMNLP 2020), GraphCodeBERT, UniXcoder, CodeReviewer, CodeExecutor, LongCoder. CodeBERT loads as a RoBERTa-style model (`microsoft/codebert-base`) via Hugging Face `transformers`; `UniXcoder/unixcoder.py` provides a wrapper aimed at code representation; a `CodeReviewer` directory exists (review-comment tasks) that may supply data for E1.
- Not yet verified: dataset licenses and download sizes; retrieval quality of each model. The ML_DESIGN benchmark decides. Disk budget is a constraint.
- Implement independently: our own embedding pipeline and benchmark; no model weights are redistributed.

## 5. GitHub App webhook documentation
- URL: https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events. Method: **not fully read** (one web search returned related docs; I did not open this page in this session).
- To study in M2: webhook payload shapes for `pull_request`, delivery redelivery behavior, response-time expectations, `X-GitHub-Delivery`, local testing with tunnels.

## 6. GitHub App best practices
- URL: https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app. Method: **docs/search** (search summary of the page).
- Observations (from the summary): choose the minimum permissions; installation tokens can be narrowed to specific repositories and permissions; set a webhook secret and verify signatures; subscribe to webhooks instead of polling to stay under rate limits, and on rate limiting use `x-ratelimit-reset` or `Retry-After`.
- Implemented in design: SECURITY.md permission list, signature verification, dedup, backoff.
- To verify when reading the full page: key storage guidance, token expiry details.

## 7. Qodo documentation
- URL: https://docs.qodo.ai/. Method: **docs/search** only (search summaries, no full page read).
- Observations: `/review` gives PR feedback on quality and security issues; reviews can be triggered by comment or run automatically when a PR is opened, reopened or marked ready; behavior is configurable through flags and a configuration file; the product describes multiple workflows (`/describe`, `/review`, `/improve`, etc.) and newer cross-repo and rule-mining features.
- Implement independently: per-repository configuration with auto/manual triggers and draft-PR policy. Differently: our feedback analytics and measured precision are first-class.
- Follow-up: read the review tool page fully and note which fields they output; not done yet.

## 8. Additional resources to study (planned)
Reviewer-quality literature on automated code review and noisy findings, SZZ-based defect labeling pitfalls, SARIF 2.1.0 spec for export, GitHub REST docs for pull request reviews and review comment positions, Semgrep rule license page, tree-sitter Python binding docs, OWASP Top 10 and ASVS for category mapping.

## Licensing and attribution note
PR-Agent is MIT licensed. We are not copying code; if any is ever adopted, its copyright and license notice must be preserved in `THIRD_PARTY_NOTICES`.
