"""Review job against the real database, with GitHub mocked (real engine, real Ruff)."""

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from lyvern.db import ReviewRun, get_engine
from lyvern.engine.policy import ReviewPolicy
from lyvern.github.models import ChangedFileInfo, MergeState, PullRequestInfo
from lyvern.github.publisher import GitHubPublisher, WriteGuard
from lyvern.github.refs import PullRequestRef
from lyvern.services.review_job import execute_review

pytestmark = pytest.mark.integration

REPO = "bhuvan-somisetty/lyvern-sandbox"
CODE = "import os\n\n\ndef f(items=[]):\n    return eval(items)\n"
PATCH = "@@ -0,0 +1,5 @@\n" + "".join(f"+{line}\n" for line in CODE.split("\n")[:-1])


CLEAN = "def add(a, b):\n    return a + b\n"
CLEAN_PATCH = "@@ -0,0 +1,2 @@\n" + "".join(f"+{line}\n" for line in CLEAN.split("\n")[:-1])


class FakeSource:
    def __init__(self, fail: bool = False, clean: bool = False) -> None:
        self.fail = fail
        self.clean = clean

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        if self.fail:
            raise RuntimeError("boom with a detail")
        return PullRequestInfo(
            owner="bhuvan-somisetty", repo="lyvern-sandbox", number=4, title="t", body="",
            author="bhuvan-somisetty", state="open", draft=False,
            html_url="https://github.com/bhuvan-somisetty/lyvern-sandbox/pull/4",
            base_ref="main", base_sha="b" * 40, head_ref="x", head_sha="a" * 40,
            head_repo_full_name=REPO, changed_files=1, additions=5, deletions=0,
        )  # fmt: skip

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        patch = CLEAN_PATCH if self.clean else PATCH
        return [
            ChangedFileInfo(
                filename="app.py", status="added", additions=5, deletions=0, patch=patch
            )
        ]

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return CLEAN if self.clean else CODE


class Recorder:
    def __init__(self, post_status: int = 200, put_status: int = 200) -> None:
        self.posts: list[dict[str, Any]] = []
        self.puts: list[str] = []
        self.post_status = post_status
        self.put_status = put_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "PUT":
            self.puts.append(request.url.path)
            return httpx.Response(self.put_status, json={})
        self.posts.append(json.loads(request.content))
        return httpx.Response(self.post_status, json={"id": 777})


@pytest.fixture
def db() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries"))
    yield


def make_run(sha: str = "a" * 40, status: str = "queued") -> UUID:
    with Session(get_engine()) as s:
        run = ReviewRun(
            repo_full_name=REPO, pr_number=4, head_sha=sha, installation_id=5,
            trigger_delivery_id="d", status=status,
        )  # fmt: skip
        s.add(run)
        s.commit()
        return run.id


def run_job(
    run_id: UUID, source: FakeSource, rec: Recorder, policy: ReviewPolicy | None = None
) -> None:
    publisher = GitHubPublisher(WriteGuard([REPO]), lambda: "t", transport=httpx.MockTransport(rec))
    execute_review(
        get_engine(),
        run_id,
        make_source=lambda _i: source,
        publisher=publisher,
        policy=policy or ReviewPolicy(),
    )


def load(run_id: UUID) -> ReviewRun:
    with Session(get_engine()) as s:
        run = s.get(ReviewRun, run_id)
        assert run is not None
        s.expunge(run)
        return run


def test_successful_review_is_published_and_recorded(db: None) -> None:
    rid, rec = make_run(), Recorder()
    run_job(rid, FakeSource(), rec)
    run = load(rid)
    assert (run.status, run.event_posted, run.github_review_id) == (
        "succeeded",
        "REQUEST_CHANGES",
        777,
    )
    assert run.findings_count and run.inline_posted and run.started_at and run.finished_at
    (post,) = rec.posts
    assert post["event"] == "REQUEST_CHANGES" and post["commit_id"] == "a" * 40
    assert "Automated pull request review" in post["body"]
    assert {c["line"] for c in post["comments"]} >= {5}  # the eval line was added by the PR


def test_a_run_that_is_not_queued_is_left_alone(db: None) -> None:
    rid, rec = make_run(status="succeeded"), Recorder()
    run_job(rid, FakeSource(), rec)
    assert rec.posts == [] and load(rid).status == "succeeded"
    run_job(UUID(int=1), FakeSource(), rec)  # unknown id: no error, no post
    assert rec.posts == []


def test_a_newer_run_for_the_same_pr_supersedes_and_nothing_is_posted(db: None) -> None:
    old = make_run(sha="a" * 40)
    make_run(sha="c" * 40)  # created later for the same pull request
    rec = Recorder()
    run_job(old, FakeSource(), rec)
    assert load(old).status == "superseded" and rec.posts == []


def test_failures_are_recorded_without_posting(db: None) -> None:
    rid, rec = make_run(), Recorder()
    run_job(rid, FakeSource(fail=True), rec)
    run = load(rid)
    assert run.status == "failed" and "RuntimeError" in (run.error or "") and rec.posts == []

    rid2, rec2 = make_run(sha="d" * 40), Recorder(post_status=500)
    run_job(rid2, FakeSource(), rec2)
    run2 = load(rid2)
    assert run2.status == "failed" and "PublishError" in (run2.error or "")


def test_publishing_to_a_repository_off_the_allowlist_fails_the_run(db: None) -> None:
    rid = make_run()
    rec = Recorder()
    publisher = GitHubPublisher(
        WriteGuard(["someone/else"]), lambda: "t", transport=httpx.MockTransport(rec)
    )
    execute_review(
        get_engine(),
        rid,
        make_source=lambda _i: FakeSource(),
        publisher=publisher,
        policy=ReviewPolicy(),
    )
    run = load(rid)
    assert run.status == "failed" and "WriteNotAllowed" in (run.error or "") and rec.posts == []


# ------------------------------------------------ dismissing our own stale "changes requested"


def make_previous_request_changes(review_id: int = 555) -> UUID:
    with Session(get_engine()) as s:
        run = ReviewRun(
            repo_full_name=REPO, pr_number=4, head_sha="9" * 40, installation_id=5,
            trigger_delivery_id="d0", status="succeeded", event_posted="REQUEST_CHANGES",
            github_review_id=review_id,
        )  # fmt: skip
        s.add(run)
        s.commit()
        return run.id


def test_clean_follow_up_dismisses_the_earlier_changes_requested_review(db: None) -> None:
    previous = make_previous_request_changes(555)
    rid, rec = make_run(sha="a" * 40), Recorder()
    run_job(rid, FakeSource(clean=True), rec)
    assert load(rid).event_posted == "COMMENT"
    assert rec.puts == [f"/repos/{REPO}/pulls/4/reviews/555/dismissals"]
    assert load(previous).changes_dismissed is True


def test_follow_up_that_still_blocks_does_not_dismiss(db: None) -> None:
    previous = make_previous_request_changes()
    rid, rec = make_run(sha="a" * 40), Recorder()
    run_job(rid, FakeSource(), rec)  # still has blocking findings
    assert load(rid).event_posted == "REQUEST_CHANGES"
    assert rec.puts == [] and load(previous).changes_dismissed is False


def test_incomplete_follow_up_never_dismisses(db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from lyvern.engine.analyzers import AnalyzerError

    def boom(*a: Any, **k: Any) -> Any:
        raise AnalyzerError("timed out")

    monkeypatch.setattr("lyvern.review_pipeline.analyze_python", boom)
    previous = make_previous_request_changes()
    rid, rec = make_run(sha="a" * 40), Recorder()
    run_job(rid, FakeSource(clean=True), rec)
    assert load(rid).status == "partial" and load(rid).event_posted == "COMMENT"
    assert rec.puts == [] and load(previous).changes_dismissed is False


def test_refused_dismissal_is_not_marked_done_and_does_not_fail_the_run(db: None) -> None:
    previous = make_previous_request_changes()
    rid, rec = make_run(sha="a" * 40), Recorder(put_status=422)
    run_job(rid, FakeSource(clean=True), rec)
    assert load(rid).status == "succeeded"  # the review itself was published
    assert load(previous).changes_dismissed is False


class ConflictingSource(FakeSource):
    def __init__(self, state: MergeState | Exception) -> None:
        super().__init__(clean=True)
        self.state = state

    def get_merge_state(self, ref: PullRequestRef) -> MergeState:
        if isinstance(self.state, Exception):
            raise self.state
        return self.state


def conflict_posts(rec: Recorder) -> list[dict[str, Any]]:
    return [p for p in rec.posts if "Merge conflicts" in str(p.get("body", ""))]


def test_a_conflicting_pull_request_gets_a_notice_and_the_run_still_succeeds(db: None) -> None:
    rid, rec = make_run(), Recorder()
    run_job(rid, ConflictingSource(MergeState(mergeable=False, state="dirty")), rec)
    assert load(rid).status == "succeeded"
    (notice,) = conflict_posts(rec)
    assert "git rebase origin/main" in notice["body"]


def test_clean_unknown_or_failing_mergeability_posts_no_notice(db: None) -> None:
    states = [
        MergeState(mergeable=True, state="clean"),
        MergeState(mergeable=None, state="unknown"),
        RuntimeError("github down"),
    ]
    for index, state in enumerate(states):
        rid, rec = make_run(sha=str(index) * 40), Recorder()
        run_job(rid, ConflictingSource(state), rec)
        assert load(rid).status == "succeeded" and conflict_posts(rec) == []


def make_previous_approval(review_id: int = 888) -> UUID:
    with Session(get_engine()) as s:
        run = ReviewRun(
            repo_full_name=REPO, pr_number=4, head_sha="8" * 40, installation_id=5,
            trigger_delivery_id="d8", status="succeeded", event_posted="APPROVE",
            github_review_id=review_id,
        )  # fmt: skip
        s.add(run)
        s.commit()
        return run.id


def test_an_earlier_approval_is_withdrawn_when_the_latest_review_does_not_approve(db: None) -> None:
    previous = make_previous_approval(888)
    rid, rec = make_run(sha="a" * 40), Recorder()
    run_job(rid, ConflictingSource(MergeState(mergeable=False, state="dirty")), rec)
    assert load(rid).event_posted == "COMMENT"
    assert rec.puts == [f"/repos/{REPO}/pulls/4/reviews/888/dismissals"]
    assert load(previous).changes_dismissed is True


def test_an_earlier_approval_stays_when_the_latest_review_approves_again(db: None) -> None:
    previous = make_previous_approval(888)
    rid, rec = make_run(sha="a" * 40), Recorder()
    run_job(rid, FakeSource(clean=True), rec, ReviewPolicy(allow_approve=True))
    assert load(rid).event_posted == "APPROVE"
    assert rec.puts == [] and load(previous).changes_dismissed is False
