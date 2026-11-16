"""A push to the target branch re-checks open pull requests for new conflicts."""

import json
from collections.abc import Collection, Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from lyvern.config import get_settings
from lyvern.db import ReviewRun, get_engine
from lyvern.github.models import MergeState, PullRequestInfo
from lyvern.github.publisher import GitHubPublisher, WriteGuard
from lyvern.github.refs import PullRequestRef
from lyvern.github.webhook import compute_signature
from lyvern.services.conflict_check import check_open_pull_requests
from lyvern_api import main as api_main

pytestmark = pytest.mark.integration

SECRET = "integration-test-secret"
REPO = "bhuvan-somisetty/lyvern-sandbox"
Queued = list[tuple[str, int, str]]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Queued]]:
    monkeypatch.setenv("LYVERN_GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("LYVERN_WRITE_ALLOWED_REPOS", REPO)
    get_settings.cache_clear()
    queued: Queued = []
    monkeypatch.setattr(api_main.check_conflicts, "delay", lambda r, i, b: queued.append((r, i, b)))
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries CASCADE"))
    yield TestClient(api_main.create_app()), queued
    get_settings.cache_clear()


def push(tc: TestClient, delivery: str, repo: str = REPO, **over: Any) -> Any:
    data: dict[str, Any] = {
        "ref": "refs/heads/main",
        "deleted": False,
        "installation": {"id": 5},
        "repository": {"full_name": repo},
        "sender": {"login": "x"},
    }
    data.update(over)
    raw = json.dumps(data).encode()
    return tc.post(
        "/webhooks/github",
        content=raw,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": compute_signature(SECRET, raw),
            "Content-Type": "application/json",
        },
    )


def test_a_push_to_an_allowed_repository_queues_a_conflict_check(
    client: tuple[TestClient, Queued],
) -> None:
    tc, queued = client
    r = push(tc, "p1")
    assert (r.status_code, r.json()["status"]) == (202, "queued")
    assert queued == [(REPO, 5, "main")]
    assert push(tc, "p1").json()["status"] == "duplicate" and len(queued) == 1  # redelivery


def test_pushes_that_must_not_be_checked_are_ignored_or_rejected(
    client: tuple[TestClient, Queued],
) -> None:
    tc, queued = client
    assert push(tc, "p2", ref="refs/tags/v1").json()["status"] == "ignored"
    assert push(tc, "p3", deleted=True).json()["status"] == "ignored"
    assert push(tc, "p4", repo="someone/else").json()["status"] == "rejected"
    assert queued == []


# ------------------------------------------------------------------ the check itself


def info(number: int, draft: bool = False) -> PullRequestInfo:
    return PullRequestInfo(
        owner="bhuvan-somisetty",
        repo="lyvern-sandbox",
        number=number,
        title="t",
        body="",
        author="a",
        state="open",
        draft=draft,
        html_url="u",
        base_ref="main",
        base_sha="b" * 40,
        head_ref=f"f{number}",
        head_sha=f"{number}" * 40,
        head_repo_full_name=REPO,
        changed_files=1,
        additions=1,
        deletions=0,
    )


class FakeSource:
    def __init__(
        self, states: dict[int, MergeState | Exception], drafts: Collection[int] = ()
    ) -> None:
        self.states, self.drafts = states, set(drafts)
        self.asked: list[int] = []

    def list_open_pull_requests(
        self, owner: str, repo: str, base: str, *, limit: int = 50
    ) -> list[PullRequestInfo]:
        return [info(n, n in self.drafts) for n in self.states]

    def get_merge_state(self, ref: PullRequestRef) -> MergeState:
        self.asked.append(ref.number)
        state = self.states[ref.number]
        if isinstance(state, Exception):
            raise state
        return state


class Recorder:
    def __init__(self) -> None:
        self.comments: list[tuple[str, str]] = []
        self.puts: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "PUT":
            self.puts.append(request.url.path)
            return httpx.Response(200, json={})
        self.comments.append((request.url.path, json.loads(request.content)["body"]))
        return httpx.Response(201, json={"id": 1})


@pytest.fixture
def db() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries CASCADE"))
    yield


def previous_approval(pr: int, review_id: int) -> UUID:
    with Session(get_engine()) as s:
        run = ReviewRun(
            repo_full_name=REPO,
            pr_number=pr,
            head_sha="8" * 40,
            installation_id=5,
            trigger_delivery_id=f"d{pr}",
            status="succeeded",
            event_posted="APPROVE",
            github_review_id=review_id,
        )
        s.add(run)
        s.commit()
        return run.id


def run_check(source: FakeSource, rec: Recorder) -> int:
    pub = GitHubPublisher(WriteGuard([REPO]), lambda: "t", transport=httpx.MockTransport(rec))
    return check_open_pull_requests(get_engine(), source, pub, REPO, "main")


def test_a_pull_request_that_now_conflicts_gets_a_notice_and_loses_its_approval(db: None) -> None:
    approval = previous_approval(7, 700)
    source = FakeSource(
        {
            7: MergeState(mergeable=False, state="dirty"),
            8: MergeState(mergeable=True, state="clean"),
        }
    )
    rec = Recorder()
    assert run_check(source, rec) == 1
    assert [p for p, _b in rec.comments] == [f"/repos/{REPO}/issues/7/comments"]
    assert "git rebase origin/main" in rec.comments[0][1]
    assert rec.puts == [f"/repos/{REPO}/pulls/7/reviews/700/dismissals"]
    with Session(get_engine()) as s:
        row = s.get(ReviewRun, approval)
        assert row is not None and row.changes_dismissed is True


def test_drafts_unknown_state_and_failures_are_skipped_without_stopping_the_rest(db: None) -> None:
    source = FakeSource(
        {
            1: MergeState(mergeable=False, state="dirty"),  # draft: skipped
            2: RuntimeError("github down"),
            3: MergeState(mergeable=None, state="unknown"),
            4: MergeState(mergeable=False, state="dirty"),
        },
        drafts={1},
    )
    rec = Recorder()
    assert run_check(source, rec) == 1
    assert source.asked == [2, 3, 4]
    assert [p for p, _b in rec.comments] == [f"/repos/{REPO}/issues/4/comments"]
