"""Plain data returned by the GitHub read client."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PullRequestInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    owner: str
    repo: str
    number: int
    title: str
    body: str
    author: str
    state: str
    draft: bool
    html_url: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    head_repo_full_name: str  # where the head commit lives (a fork for fork PRs)
    changed_files: int
    additions: int
    deletions: int


class MergeState(BaseModel):
    """Whether GitHub can merge the pull request. ``mergeable`` is None while it computes."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    mergeable: bool | None
    state: str  # GitHub's mergeable_state: clean, dirty (conflicts), blocked, behind, unknown, ...

    @property
    def has_conflicts(self) -> bool:
        return self.mergeable is False and self.state == "dirty"


class ChangedFileInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    filename: str
    status: str  # added, removed, modified, renamed, copied, changed, unchanged
    additions: int
    deletions: int
    patch: str | None = None  # absent for binary or very large files
    previous_filename: str | None = None


class ReviewCommentInfo(BaseModel):
    """An inline review comment written on a pull request (by a person or a bot)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    path: str
    body: str
    author: str
    author_type: str  # "User" or "Bot"
    line: int | None = None
    original_line: int | None = None
    in_reply_to_id: int | None = None

    @property
    def anchor_line(self) -> int | None:
        return self.line if self.line is not None else self.original_line
