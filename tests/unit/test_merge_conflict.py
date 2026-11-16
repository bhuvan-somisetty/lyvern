"""Merge-conflict notice: text, mergeability polling, once-per-commit posting, write guard."""

import json
from typing import Any

import httpx
import pytest

from lyvern.engine.conflict import conflict_marker, has_conflict_marker, render_conflict_notice
from lyvern.github.client import GitHubReadClient
from lyvern.github.models import MergeState
from lyvern.github.publisher import GitHubPublisher, PublishError, WriteGuard, WriteNotAllowed
from lyvern.github.refs import PullRequestRef

SHA = "a1b2c3d" * 5 + "e1f2a"
REF = PullRequestRef("octo", "repo", 4)


def test_notice_explains_the_fix_and_carries_the_marker_and_no_emoji() -> None:
    text = render_conflict_notice("main", "feature/x", SHA)
    assert "git rebase origin/main" in text and "git checkout feature/x" in text
    assert "--force-with-lease" in text and "git merge origin/main" in text
    assert has_conflict_marker(text, SHA) and not has_conflict_marker(text, "b" * 40)
    assert conflict_marker(SHA) in text
    assert all(ord(c) < 0x2190 for c in text)  # plain text, no emoji or symbols


def test_hostile_branch_names_never_reach_the_commands() -> None:
    text = render_conflict_notice("main", "x`\n```\nrm -rf /", SHA)
    assert "rm -rf" not in text and "git checkout <your-branch>" in text
    flag = render_conflict_notice("--upload-pack=evil", "ok", SHA)
    assert "--upload-pack" not in flag and "<base-branch>" in flag
    with pytest.raises(ValueError):
        render_conflict_notice("main", "ok", "not a sha")


def test_only_a_dirty_unmergeable_state_counts_as_conflicts() -> None:
    assert MergeState(mergeable=False, state="dirty").has_conflicts
    assert not MergeState(mergeable=False, state="blocked").has_conflicts
    assert not MergeState(mergeable=True, state="clean").has_conflicts
    assert not MergeState(mergeable=None, state="unknown").has_conflicts


def client_with(responses: list[dict[str, Any]]) -> tuple[GitHubReadClient, list[str]]:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=responses[min(len(paths) - 1, len(responses) - 1)])

    return GitHubReadClient("t", transport=httpx.MockTransport(handler)), paths


def test_merge_state_asks_again_while_github_is_still_computing() -> None:
    client, paths = client_with(
        [
            {"mergeable": None, "mergeable_state": "unknown"},
            {"mergeable": None, "mergeable_state": "unknown"},
            {"mergeable": False, "mergeable_state": "dirty"},
        ]
    )
    sleeps: list[float] = []
    state = client.get_merge_state(REF, sleep=sleeps.append)
    assert state.has_conflicts and len(paths) == 3 and len(sleeps) == 2


def test_merge_state_gives_up_as_unknown_instead_of_guessing() -> None:
    client, paths = client_with([{"mergeable": None, "mergeable_state": "unknown"}])
    state = client.get_merge_state(REF, attempts=3, sleep=lambda _s: None)
    assert state.mergeable is None and not state.has_conflicts and len(paths) == 3


class Recorder:
    def __init__(self, existing: list[dict[str, Any]], post_status: int = 201) -> None:
        self.existing, self.post_status = existing, post_status
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=self.existing)
        self.posts.append((request.url.path, json.loads(request.content)))
        return httpx.Response(self.post_status, json={"id": 1})


def publisher(rec: Recorder, allowed: str = "octo/repo") -> GitHubPublisher:
    return GitHubPublisher(WriteGuard([allowed]), lambda: "t", transport=httpx.MockTransport(rec))


def test_notice_is_posted_once_per_head_commit() -> None:
    body = render_conflict_notice("main", "x", SHA)
    rec = Recorder([])
    assert publisher(rec).post_conflict_notice("octo/repo", 4, body, SHA) is True
    assert rec.posts == [("/repos/octo/repo/issues/4/comments", {"body": body})]

    again = Recorder([{"body": "hello"}, {"body": body}])
    assert publisher(again).post_conflict_notice("octo/repo", 4, body, SHA) is False
    assert again.posts == []

    new_commit = "f" * 40  # a newer push that still conflicts gets a fresh notice
    newer = Recorder([{"body": body}])
    body2 = render_conflict_notice("main", "x", new_commit)
    assert publisher(newer).post_conflict_notice("octo/repo", 4, body2, new_commit) is True


def test_notice_respects_the_write_allowlist_and_reports_failures() -> None:
    rec = Recorder([])
    with pytest.raises(WriteNotAllowed):
        publisher(rec, allowed="someone/else").post_conflict_notice("octo/repo", 4, "b", SHA)
    assert rec.posts == []
    with pytest.raises(PublishError, match="HTTP 403"):
        publisher(Recorder([], post_status=403)).post_conflict_notice("octo/repo", 4, "b", SHA)
