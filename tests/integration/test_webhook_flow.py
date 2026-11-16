"""Webhook endpoint + ingestion against the real database (run `alembic upgrade head` first)."""

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from lyvern.config import get_settings
from lyvern.db import ReviewRun, WebhookDelivery, get_engine
from lyvern.github.webhook import compute_signature
from lyvern_api import main as api_main

pytestmark = pytest.mark.integration

SECRET = "integration-test-secret"
REPO = "bhuvan-somisetty/lyvern-sandbox"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[str]]]:
    monkeypatch.setenv("LYVERN_GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("LYVERN_WRITE_ALLOWED_REPOS", REPO)
    get_settings.cache_clear()
    queued: list[str] = []
    monkeypatch.setattr(api_main.run_review, "delay", lambda run_id: queued.append(run_id))
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries CASCADE"))
    yield TestClient(api_main.create_app()), queued
    get_settings.cache_clear()


def payload(action: str = "opened", repo: str = REPO, sha: str = "a" * 40) -> dict[str, Any]:
    return {
        "action": action,
        "installation": {"id": 5},
        "repository": {"full_name": repo},
        "sender": {"login": "bhuvan-somisetty"},
        "pull_request": {
            "number": 4,
            "draft": False,
            "user": {"login": "bhuvan-somisetty"},
            "head": {"sha": sha, "ref": "feature"},
            "base": {"sha": "b" * 40, "ref": "main"},
        },
    }


def send(
    tc: TestClient,
    data: Any,
    *,
    delivery: str = "del-1",
    event: str = "pull_request",
    secret: str = SECRET,
    raw: bytes | None = None,
) -> Any:
    body = raw if raw is not None else json.dumps(data).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": compute_signature(secret, body),
        "Content-Type": "application/json",
    }
    return tc.post("/webhooks/github", content=body, headers=headers)


def counts() -> tuple[int, int]:
    with Session(get_engine()) as s:
        return (
            s.scalar(select(func.count()).select_from(WebhookDelivery)) or 0,
            s.scalar(select(func.count()).select_from(ReviewRun)) or 0,
        )


def test_bad_or_missing_signature_is_rejected_and_nothing_is_stored(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    assert send(tc, payload(), secret="wrong").status_code == 401
    unsigned = tc.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "x"},
    )
    assert unsigned.status_code == 401
    assert counts() == (0, 0) and queued == []


def test_valid_pull_request_is_recorded_and_queued_once(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    response = send(tc, payload())
    assert response.status_code == 202 and response.json()["status"] == "queued"
    assert counts() == (1, 1) and len(queued) == 1
    assert UUID(queued[0]) == UUID(response.json()["run_id"])
    with Session(get_engine()) as s:
        run = s.scalars(select(ReviewRun)).one()
        assert (run.repo_full_name, run.pr_number, run.head_sha, run.status) == (
            REPO,
            4,
            "a" * 40,
            "queued",
        )
        assert run.installation_id == 5


def test_redelivery_of_the_same_delivery_id_does_nothing(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    assert send(tc, payload()).status_code == 202
    again = send(tc, payload())
    assert again.status_code == 200 and again.json()["status"] == "duplicate"
    assert counts() == (1, 1) and len(queued) == 1


def test_new_delivery_for_an_already_reviewed_commit_is_not_reviewed_again(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    assert send(tc, payload(), delivery="d1").status_code == 202
    second = send(tc, payload(action="reopened"), delivery="d2")
    assert second.status_code == 200 and second.json()["status"] == "duplicate_run"
    assert counts() == (2, 1) and len(queued) == 1  # delivery recorded, no second run
    third = send(tc, payload(action="synchronize", sha="c" * 40), delivery="d3")
    assert third.status_code == 202 and counts() == (3, 2) and len(queued) == 2  # new commit


def test_repository_outside_the_write_allowlist_is_never_queued(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    response = send(tc, payload(repo="jaegertracing/jaeger-ui"))
    assert response.status_code == 202 and response.json()["status"] == "rejected"
    assert counts() == (1, 0) and queued == []
    with Session(get_engine()) as s:
        assert s.scalars(select(WebhookDelivery)).one().status == "rejected"


def test_other_events_and_non_review_actions_are_ignored(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    assert send(tc, {"zen": "hi"}, event="ping", delivery="p1").json()["status"] == "ignored"
    assert send(tc, payload(action="closed"), delivery="p2").json()["status"] == "ignored"
    assert send(tc, payload(action="labeled"), delivery="p3").json()["status"] == "ignored"
    assert counts() == (3, 0) and queued == []


def test_malformed_payload_with_valid_signature_is_a_400(
    client: tuple[TestClient, list[str]],
) -> None:
    tc, queued = client
    assert send(tc, None, raw=b'{"action":"opened"}').status_code == 400
    assert send(tc, None, raw=b"not json", delivery="x2").status_code == 400
    assert queued == []


def test_oversized_body_is_refused(client: tuple[TestClient, list[str]]) -> None:
    tc, _ = client
    big = b"{" + b" " * (api_main.MAX_WEBHOOK_BYTES + 10) + b"}"
    assert send(tc, None, raw=big).status_code == 413
