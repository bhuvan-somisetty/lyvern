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

## 5. How to reproduce
```bash
uv run lyvern benchmark synthetic
uv run lyvern benchmark real --prs prs.txt --tolerance 3 --sheet sheet.jsonl
```
`prs.txt`: one `owner/repo#N` or PR URL per line. The command only reads from GitHub.

## 6. Known limitations
Small samples (30 PRs, 43 human comments); three repositories, two ecosystems; location matching is a proxy for "same issue"; human comments include questions and nits; no labelled precision yet; synthetic cases are author-written; the benchmark covers the static layer only until the AI layer is measured.
