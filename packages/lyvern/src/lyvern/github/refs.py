"""Parse a pull request reference given as a URL or ``owner/repo#number``."""

from __future__ import annotations

import re
from dataclasses import dataclass

_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/pull/(?P<number>\d+)(?:[/?#].*)?$"
)
_SHORT = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>\d+)$")


class InvalidPullRequestRef(ValueError):
    pass


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int

    def __str__(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_pr_reference(text: str) -> PullRequestRef:
    cleaned = text.strip()
    match = _URL.match(cleaned) or _SHORT.match(cleaned)
    if match is None:
        raise InvalidPullRequestRef(
            f"not a pull request reference: {text!r} "
            "(use https://github.com/owner/repo/pull/123 or owner/repo#123)"
        )
    number = int(match["number"])
    if number < 1:
        raise InvalidPullRequestRef("pull request number must be positive")
    return PullRequestRef(match["owner"], match["repo"], number)
