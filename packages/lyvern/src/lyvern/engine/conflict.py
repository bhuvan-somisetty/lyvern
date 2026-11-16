"""The message posted when a pull request cannot be merged because of conflicts.

Lyvern does not edit the author's branch. It tells them what is wrong and how to fix it,
once per head commit (a hidden marker keeps it from being posted twice).
"""

from __future__ import annotations

import re

MARKER_PREFIX = "<!-- lyvern:merge-conflict:"
_SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def conflict_marker(head_sha: str) -> str:
    return f"{MARKER_PREFIX}{head_sha} -->"


def has_conflict_marker(body: str, head_sha: str) -> bool:
    return conflict_marker(head_sha) in body


def _ref(name: str, fallback: str) -> str:
    # branch names come from the PR author: only plain ref characters go into the commands
    return name if _SAFE_REF.fullmatch(name) and not name.startswith("-") else fallback


def render_conflict_notice(base_ref: str, head_ref: str, head_sha: str) -> str:
    if not _SHA.fullmatch(head_sha):
        raise ValueError("head_sha must be a hex commit id")
    base = _ref(base_ref, "<base-branch>")
    head = _ref(head_ref, "<your-branch>")
    return (
        "**Merge conflicts (Lyvern)**\n\n"
        f"This pull request has merge conflicts with `{base}`, so GitHub cannot merge it until "
        "they are resolved. Lyvern does not change your branch; here is how to fix it.\n\n"
        f"Rebase onto the latest `{base}` (use the remote that points at this repository):\n\n"
        "```\n"
        "git fetch origin\n"
        f"git checkout {head}\n"
        f"git rebase origin/{base}\n"
        "# git lists the conflicting files: open each one, keep the right lines,\n"
        "# then mark it resolved and continue\n"
        "git add <the files you fixed>\n"
        "git rebase --continue\n"
        "git push --force-with-lease\n"
        "```\n\n"
        f"If you prefer not to rewrite history, run `git merge origin/{base}` instead and push "
        "normally. You can also use the **Resolve conflicts** button below the PR for simple "
        "cases.\n\n"
        "Pushing the fix triggers a fresh review.\n\n"
        f"{conflict_marker(head_sha)}"
    )
