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


class ChangedFileInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    filename: str
    status: str  # added, removed, modified, renamed, copied, changed, unchanged
    additions: int
    deletions: int
    patch: str | None = None  # absent for binary or very large files
    previous_filename: str | None = None
