"""Collect a labelled dataset of real pull requests from public repositories (read-only).

Two files, so a change to the features never needs the data to be fetched again:

* ``prs_raw.jsonl`` is the source of truth: for each pull request its metadata, the list of
  changed files (names, statuses, line counts; no code) and the human-review labels. It holds
  third parties' usernames and PR text, so it stays on the owner's machine (git-ignored).
* ``prs.csv`` is derived from it by ``featurize`` using ``lyvern.ml.features``. It has numbers
  only (repository, PR number, date, labels, features): no usernames, titles or text.

Labels: ``changes_requested`` = a person other than the author submitted a CHANGES_REQUESTED
review; ``human_reviewed`` = any non-author, non-bot review; ``human_inline_comments`` = number
of top-level inline review comments written by a person other than the author.

This module only reads from GitHub (``GitHubReadClient`` has no write methods). It resumes from
an existing file, stops cleanly at the rate limit, and skips bot-authored pull requests.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from lyvern.github.client import GitHubError, GitHubRateLimited, GitHubReadClient
from lyvern.github.models import (
    ChangedFileInfo,
    PullRequestInfo,
    ReviewCommentInfo,
    ReviewInfo,
)
from lyvern.github.refs import PullRequestRef
from lyvern.ml.features import FEATURE_NAMES, extract_features

META_FIELDS = ("repo", "number", "created_at", "merged")  # no usernames in the committed CSV
LABEL_FIELDS = ("changes_requested", "human_reviewed", "human_inline_comments")
FIELDS = (*META_FIELDS, *LABEL_FIELDS, *FEATURE_NAMES)
MAX_BODY_CHARS = 20_000


def human_inline_comment_count(pr_author: str, comments: Iterable[ReviewCommentInfo]) -> int:
    """Top-level inline comments written by a person other than the author (replies excluded)."""
    return sum(
        1
        for c in comments
        if c.author_type == "User"
        and c.author
        and c.author != pr_author
        and c.in_reply_to_id is None
    )


def human_review_labels(
    pr_author: str,
    reviews: Iterable[ReviewInfo],
    comments: Iterable[ReviewCommentInfo] = (),
) -> dict[str, int]:
    humans = [r for r in reviews if r.author_type == "User" and r.author and r.author != pr_author]
    return {
        "changes_requested": int(any(r.state == "CHANGES_REQUESTED" for r in humans)),
        "human_reviewed": int(bool(humans)),
        "human_inline_comments": human_inline_comment_count(pr_author, comments),
    }


def is_bot(login: str) -> bool:
    lowered = login.lower()
    return lowered.endswith("[bot]") or lowered in {"dependabot", "renovate", "github-actions"}


def load_raw(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_done(path: Path) -> set[tuple[str, int]]:
    return {(rec["repo"], int(rec["number"])) for rec in load_raw(path)}


def _record(
    full_name: str,
    pr: PullRequestInfo,
    files: list[ChangedFileInfo],
    labels: dict[str, int],
) -> dict[str, Any]:
    meta = pr.model_dump()
    meta["body"] = (meta.get("body") or "")[:MAX_BODY_CHARS]
    return {
        "repo": full_name,
        "number": pr.number,
        "pr": meta,
        "files": [f.model_dump(exclude={"patch"}) for f in files],
        "labels": labels,
    }


def collect_repo(
    client: GitHubReadClient,
    full_name: str,
    out: Path,
    *,
    target: int,
    done: set[tuple[str, int]],
    log: Callable[[str], None] = print,
    max_scan: int | None = None,
    workers: int = 6,
) -> tuple[int, bool]:
    """Append up to ``target`` new records for one repository. Returns (added, rate_limited)."""
    owner, _, repo = full_name.partition("/")
    have = sum(1 for r, _n in done if r == full_name)
    wanted = max(0, target - have)
    if wanted == 0:
        return 0, False
    scan_limit = max_scan or wanted * 4 + have
    candidates = client.list_pull_requests(owner, repo, state="closed", limit=scan_limit)
    todo = [c for c in candidates if (full_name, c.number) not in done and not is_bot(c.author)]
    todo = todo[: wanted + max(5, wanted // 8)]  # a little extra to cover skipped pull requests

    def fetch(listed: PullRequestInfo) -> tuple[str, dict[str, Any] | None]:
        ref = PullRequestRef(owner, repo, listed.number)
        try:
            pr = client.get_pull_request(ref)
            if pr.changed_files == 0:
                return "skip", None
            files = client.list_changed_files(ref)
            reviews = client.list_reviews(ref)
            comments = client.list_review_comments(ref)
        except GitHubRateLimited:
            return "limited", None
        except GitHubError as error:
            log(f"{full_name}#{listed.number}: skipped ({error})")
            return "skip", None
        labels = human_review_labels(pr.author, reviews, comments)
        return "ok", _record(full_name, pr, files, labels)

    added = 0
    limited = False
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=workers) as pool:
        for status, record in pool.map(fetch, todo):
            if status == "limited":
                limited = True
                break
            if status != "ok" or record is None or added >= wanted:
                continue
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            done.add((full_name, int(record["number"])))
            added += 1
            if added % 25 == 0:
                log(f"{full_name}: {added}/{wanted}")
    if limited:
        log(f"{full_name}: rate limit reached after {added} records")
    return added, limited


def collect(
    client: GitHubReadClient,
    repos: Iterable[str],
    out: Path,
    *,
    per_repo: int,
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    done = load_done(out)
    total = 0
    for full_name in repos:
        added, limited = collect_repo(client, full_name, out, target=per_repo, done=done, log=log)
        total += added
        log(f"{full_name}: +{added} records")
        if limited:
            log("stopping at the GitHub rate limit; run the same command again later to resume")
            break
        sleep(0)
    return total


def featurize(raw: Path, out_csv: Path) -> int:
    """Rebuild the feature CSV from the raw records (no network). Returns the row count."""
    rows = 0
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for rec in load_raw(raw):
            pr = PullRequestInfo(**rec["pr"])
            files = [ChangedFileInfo(**f) for f in rec["files"]]
            row: dict[str, object] = {
                "repo": rec["repo"],
                "number": rec["number"],
                "created_at": pr.created_at,
                "merged": int(pr.merged),
                **rec["labels"],
            }
            row.update({k: round(v, 6) for k, v in extract_features(pr, files).items()})
            writer.writerow(row)
            rows += 1
    return rows
