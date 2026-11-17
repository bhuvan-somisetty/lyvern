# Benchmark: methodology and measured results

Everything here was measured by running the code in this repository. Numbers are quoted with sample sizes and 95% Wilson confidence intervals. Nothing is estimated or rounded up. Date of the runs: 2026-11-16.

## 1. What is measured, and what is not
| Benchmark | Question | Strength | Main weakness |
|---|---|---|---|
| Synthetic suite | Do the analysers flag known-bad code and stay quiet on known-good code? | Fast regression check, deterministic | The author wrote both the rules and the cases, so it says nothing about real-world accuracy |
| Real-PR comparison | On real merged PRs, how often does Lyvern raise findings, and do they overlap with what human reviewers wrote? | Real code, real reviewers | Human comments are mostly design/style; overlap is a coverage figure, not accuracy; precision needs human labels |
| Labelled precision (adjudication sheet) | Of the findings Lyvern would post, how many are correct? | The honest precision measure | Needs a person to label each finding; none labelled yet (there were no findings to label) |

## 2. Synthetic suite (`lyvern benchmark synthetic`)
- 61 cases: 31 that must be flagged (Python and JS/TS), 30 that must stay quiet.
- **First run: precision 31/43 = 72.1%, recall 31/31.** All 12 "unexpected" findings were Ruff `F821` (undefined name) on snippets that used undefined variables. The analyser was right; the labels were wrong. The cases were corrected to be self-contained; the analyser was not changed.
- **Corrected run: precision 31/31 = 100.0% (95% CI 89.0-100.0%), recall 31/31 = 100.0% (95% CI 89.0-100.0%), no disagreements.**
- Reading: this is a regression guard. It must not be quoted as accuracy on real code.

## 3. JS/TS analyser noise on real source (read-only scan)
- 109 non-test source files (every 7th file) from `jaegertracing/jaeger-ui` (60) and `joinmarket-webui/jam` (50): 14,025 lines, 1.1-1.7 s.
- First run: 2 findings, **both false positives** (Storybook fixtures with `hashedPassword` set to a 64-hex digest of "test"). Fixed: `.stories.` files are fixtures and a bare hex digest is not a credential. Rescan: **0 findings.**
- Caveat: the fix was tuned on this same sample, and the sample contained no true issues, so this measures noise only, not detection.

## 4. Real-PR comparison (`lyvern benchmark real`), static analysis only
- 30 recently merged/closed public PRs that received at least 2 inline review comments: 12 from `jaegertracing/jaeger-ui`, 6 from `joinmarket-webui/jam`, 12 from `The-PR-Agent/pr-agent`. Read-only; nothing was posted.
- 260 source files considered, 13 not analysed (unsupported or unavailable).
- **Findings reported on the PRs' own changes: 0 of 30 PRs (95% CI 0.0-11.4%).** 8 findings existed only in untouched code (Ruff `S104`, `S112`, `S310`, `S506`, `S608` in `pr-agent`) and were correctly NOT reported.
- **Human coverage: 0 of 43 human inline comments** had a Lyvern finding within +/-3 lines (95% CI 0.0-8.2%). Human comments per repo: jaeger-ui 18, jam 9, pr-agent 16.
- Why: a sample of the human comments shows what reviewers actually raise: "use the `useConfig()` hook instead of `getConfig()`", "this runs on every mount so the chunk downloads even when unused", "needs i18n keys", "this check is copy-pasted three times", "why are there no tests for this". These need repository conventions, behaviour and intent; pattern-based static rules cannot see them.
- Reading: static analysis alone is quiet and safe on well-reviewed code (it would have posted zero comments on these 30 PRs) but gives no coverage of what human reviewers discuss. That is the case for the AI layer, and this harness is how its value will be measured: coverage, agreement, and labelled precision.

## 5. AI layer on real PRs (`lyvern benchmark real --llm groq`), 12 PRs
Model: `openai/gpt-oss-120b` on Groq's free tier. 6 jaeger-ui PRs and 6 jam PRs (the first 6 of each in the 30-PR list). Read-only; only public code was sent, secrets redacted.
- The AI stage was unreliable on the free tier, which is itself a finding. Four runs of the same 12 PRs: first run AI ran on 2/12 PRs (5 rate-limit errors, 4 "request too large", 1 JSON-mode error); after smaller prompts, retry-after handling and pacing: 9/12; after a retry without strict JSON mode: **10/12** (the 2 failures were the model returning invalid JSON; those runs kept their static results and said "AI review could not run").
- **Result of the final run:** 8 AI observations on 5 of 12 PRs (41.7%, 95% CI 19.3-68.0%); 0 of 12 human inline comments on these PRs had a finding within +/-3 lines (95% CI 0.0-24.3%); **0 of 8 AI observations near a human comment** (95% CI 0.0-32.4%). The evidence check discarded 0 observations in the final run (all quoted real added code).
- **Run-to-run variation:** the count of observations changed between runs (5, 2, 6, 8) partly because different PRs failed each time, and a model run is not deterministic. Any single run should be read with that in mind.
- **Quality, honestly:** precision is UNKNOWN until a person labels the 8 observations in the adjudication sheet. The author's quick reading (not ground truth) suggests several are likely false positives: two warn about `currentSchedule?.x.y` although optional chaining already prevents the crash; two flag tests that expect raw i18n keys, which is what the test mocks return; a couple are plausible (a removed `outline: none` focus style; a read-only set cast). If most are false, the AI layer in its current prompt would be noisy, and the evidence check proves only that the quoted code exists, not that the claim is true.
- What would improve it (not done): repository context (conventions, related files), a second verification pass per finding, a stricter prompt about language semantics, and labelled data to measure each change.

## 5. How to reproduce
```bash
uv run lyvern benchmark synthetic
uv run lyvern benchmark real --prs prs.txt --tolerance 3 --sheet sheet.jsonl
```
`prs.txt`: one `owner/repo#N` or PR URL per line. The command only reads from GitHub.

## 6. Known limitations
Small samples (30 PRs, 43 human comments; the AI run used 12 PRs and 12 human comments); free-tier models and rate limits; non-deterministic model output; three repositories, two ecosystems; location matching is a proxy for "same issue"; human comments include questions and nits; no labelled precision yet; synthetic cases are author-written; the benchmark covers the static layer only until the AI layer is measured.

## 7. First evaluation on code the analysers had never seen (2026-11-17)

Six public repositories that were never used to tune any rule: `psf/requests`, `pallets/click`,
`gin-gonic/gin`, `spf13/cobra`, `sindresorhus/got`, `fastify/fastify` (shallow clones, source
files only, test and example directories skipped, default settings). Every finding was read in its
surrounding code and judged by the author of this repository's tooling, so the labels are one
person's judgement, not an independent panel.

- **Before the fixes: 54 findings, 9 judged correct, 45 false alarms. Precision 9/54 = 16.7%
  (95% Wilson CI 9.0%-28.7%).** 49 of the 54 came from one repository (`requests`), so the
  independent evidence is thinner than the count suggests.
- Causes of the 45 false alarms: 34 unused-import reports on re-export and compatibility modules
  (`__init__.py`, `compat.py`), 4 bare attribute reads that are deliberate property side effects
  (`response.content`), 3 disabled-TLS reports in a benchmark script that targets localhost, 2
  constant-`setattr` style reports, 1 `os.startfile` report, 1 `@ts-ignore` that carried a written
  reason.
- **What changed (all covered by `tests/unit/test_fresh_code_noise.py`):** unused imports are ignored
  in `__init__.py` and in any file with five or more of them; attribute reads as statements are no
  longer reported as useless expressions; the constant-`setattr` and `os.startfile` style rules are
  off; `@ts-ignore` with a written reason is accepted (a bare one and any `@ts-nocheck` still count);
  security rules skip `benchmark/` and `examples/` code like they already skipped tests.
- **After the fixes, the same sample gives 9 findings** (all "`warnings.warn` without `stacklevel`",
  judged correct but minor). That is an in-sample result: the fixes were designed from these very
  findings, so it must not be quoted as accuracy. A genuinely fresh batch is still needed to show
  the improvement holds.
- Quiet by design: the Go and JS/TS analysers produced 0 findings on `gin` and `cobra`, and 4 on
  `got` and `fastify` combined (the ones above).
