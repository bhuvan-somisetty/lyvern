"""Command line: ``lyvern review <PR URL or owner/repo#N>``.

Reviewer mode prints a DRAFT review for a human to read. It cannot post anything:
it only uses the read-only GitHub client.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence

from lyvern.github.client import GitHubError, GitHubRateLimited, GitHubReadClient
from lyvern.github.refs import InvalidPullRequestRef, parse_pr_reference
from lyvern.llm.base import LlmError
from lyvern.llm.factory import make_llm_reviewer
from lyvern.review_pipeline import DraftReview, review_pull_request


def resolve_token() -> str | None:
    """GITHUB_TOKEN / GH_TOKEN, else the GitHub CLI's login. Read-only use only."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = (proc.stdout or "").strip()
    return token or None


def format_draft(draft: DraftReview) -> str:
    pr = draft.pr
    lines = [
        "=" * 72,
        "DRAFT REVIEW - NOTHING WAS POSTED. Read it, verify each point, post it yourself.",
        "=" * 72,
        f"PR: {pr.html_url}",
        f"Title: {pr.title}  (by {pr.author}, {pr.state}{', draft' if pr.draft else ''})",
        f"Head: {pr.head_ref} @ {pr.head_sha[:8]}",
        f"PR size: {pr.changed_files} files changed (+{pr.additions} / -{pr.deletions}); "
        "docs, config and lock files are not analysed",
        "",
        f"Proposed verdict: {draft.decision.event.value}",
        "(Proposed only. This tool never submits reviews.)",
        "",
        draft.summary,
    ]
    if draft.inline:
        lines += ["", "-" * 72, "Proposed inline comments", "-" * 72]
        for path, line, start, text in draft.inline:
            where = f"{path}:{start}-{line}" if start else f"{path}:{line}"
            lines += ["", f"### {where}", text]
    if draft.placement.dropped:
        lines += ["", "-" * 72, "Not reported (not introduced by this PR)", "-" * 72]
        for item in draft.placement.dropped:
            f = item.finding
            lines.append(f"- {f.file_path}:{f.line_start} {f.title} ({item.reason})")
    lines += ["", "Nothing was posted to GitHub."]
    return "\n".join(lines)


def draft_to_json(draft: DraftReview) -> dict[str, object]:
    return {
        "posted": False,
        "pr": draft.pr.model_dump(),
        "proposed_event": draft.decision.event.value,
        "reasons": list(draft.decision.reasons),
        "incomplete": draft.decision.incomplete,
        "risk": {
            "score": draft.risk.score,
            "level": draft.risk.level,
            "factors": [
                {"name": x.name, "points": x.points, "reason": x.reason} for x in draft.risk.factors
            ],
        },
        "summary": draft.summary,
        "inline": [
            {"path": p, "line": ln, "start_line": st, "body": body}
            for p, ln, st, body in draft.inline
        ],
        "not_analyzed": [{"path": p, "reason": r} for p, r in draft.unanalyzed],
        "findings": [f.model_dump(mode="json") for f in draft.findings],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lyvern", description="Pull request review assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="print a DRAFT review of a pull request (never posts)")
    review.add_argument("pr", help="https://github.com/owner/repo/pull/123 or owner/repo#123")
    review.add_argument("--json", action="store_true", help="machine-readable output")
    review.add_argument(
        "--llm",
        choices=["gemini", "groq"],
        help="also ask an AI model (changed code is sent to the provider, secrets redacted)",
    )
    bench = sub.add_parser("benchmark", help="measure the analysers (read-only)")
    bsub = bench.add_subparsers(dest="bench_command", required=True)
    bsub.add_parser("synthetic", help="labelled synthetic suite (regression check)")
    real = bsub.add_parser("real", help="compare with human review comments on real public PRs")
    real.add_argument("--prs", required=True, help="text file: one PR URL or owner/repo#N per line")
    real.add_argument("--tolerance", type=int, default=3, help="line distance for a match")
    real.add_argument("--sheet", help="write the adjudication sheet (JSON lines) to this path")
    real.add_argument("--llm", choices=["gemini", "groq"], help="include the AI reviewer")
    return parser


def run_benchmark(args: argparse.Namespace) -> int:
    from lyvern.benchmark.real_prs import run_real_benchmark, write_adjudication_sheet
    from lyvern.benchmark.synthetic import run_synthetic

    if args.bench_command == "synthetic":
        print(run_synthetic().render())
        return 0
    refs = []
    with open(args.prs, encoding="utf-8") as handle:
        for raw in handle:
            text = raw.strip()
            if text and not text.startswith("#"):
                refs.append(parse_pr_reference(text))
    client = GitHubReadClient(resolve_token())
    try:
        report = run_real_benchmark(client, refs, args.tolerance, llm=make_llm_reviewer(args.llm))
    finally:
        client.close()
    print(report.render())
    if args.sheet:
        write_adjudication_sheet(report, args.sheet)
        print(f"\nAdjudication sheet written to {args.sheet} ({len(report.adjudication)} findings)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "benchmark":
        try:
            return run_benchmark(args)
        except (InvalidPullRequestRef, OSError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    try:
        ref = parse_pr_reference(args.pr)
    except InvalidPullRequestRef as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        reviewer = make_llm_reviewer(args.llm)
    except LlmError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if reviewer is not None:
        print(
            f"Note: changed code (secrets redacted) is sent to {args.llm} for the AI review.",
            file=sys.stderr,
        )
    client = GitHubReadClient(resolve_token())
    try:
        draft = review_pull_request(client, ref, llm=reviewer)
    except GitHubRateLimited as error:
        print(
            f"error: GitHub rate limit reached (resets at epoch {error.reset_epoch}).",
            file=sys.stderr,
        )
        return 3
    except GitHubError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    finally:
        client.close()
    print(json.dumps(draft_to_json(draft), indent=2) if args.json else format_draft(draft))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
