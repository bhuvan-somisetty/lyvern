"""Read-only dashboard API against the real (test) database."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from lyvern.config import get_settings
from lyvern.db import ReviewRun, WebhookDelivery, get_engine
from lyvern_api import main as api_main

pytestmark = pytest.mark.integration

TOKEN = "dashboard-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LYVERN_API_TOKEN", TOKEN)
    get_settings.cache_clear()
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries"))
    yield TestClient(api_main.create_app())
    get_settings.cache_clear()


def seed() -> list[str]:
    ids: list[str] = []
    with Session(get_engine()) as s:
        rows = [
            ("o/a", 1, "a" * 40, "succeeded", "REQUEST_CHANGES", 5, 5, True),
            ("o/a", 1, "b" * 40, "succeeded", "COMMENT", 0, 0, False),
            ("o/b", 2, "c" * 40, "failed", None, None, None, False),
        ]
        for repo, pr, sha, status, event, findings, inline, dismissed in rows:
            run = ReviewRun(
                id=uuid4(), repo_full_name=repo, pr_number=pr, head_sha=sha, installation_id=1,
                trigger_delivery_id="d", status=status, event_posted=event, findings_count=findings,
                inline_posted=inline, changes_dismissed=dismissed,
                error="boom" if status == "failed" else None,
            )  # fmt: skip
            s.add(run)
            ids.append(str(run.id))
        s.add(WebhookDelivery(delivery_id="x1", event="pull_request", status="queued"))
        s.add(WebhookDelivery(delivery_id="x2", event="ping", status="ignored"))
        s.commit()
    return ids


def test_locked_by_default_when_no_token_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LYVERN_API_TOKEN", raising=False)
    monkeypatch.setenv("LYVERN_API_TOKEN", "")
    get_settings.cache_clear()
    tc = TestClient(api_main.create_app())
    for path in ("/api/v1/runs", "/api/v1/stats", f"/api/v1/runs/{uuid4()}"):
        assert tc.get(path, headers=AUTH).status_code == 503
    get_settings.cache_clear()


def test_missing_or_wrong_token_is_rejected_on_every_endpoint(client: TestClient) -> None:
    seed()
    for path in ("/api/v1/runs", "/api/v1/stats", f"/api/v1/runs/{uuid4()}"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get(path, headers={"Authorization": TOKEN + "x"}).status_code == 401
    assert client.get("/api/v1/runs", headers=AUTH).status_code == 200


def test_empty_database_returns_honest_empty_results(client: TestClient) -> None:
    assert client.get("/api/v1/runs", headers=AUTH).json() == []
    stats = client.get("/api/v1/stats", headers=AUTH).json()
    assert (
        stats["runs_total"] == 0 and stats["findings_total"] == 0 and stats["last_run_at"] is None
    )


def test_runs_list_filters_and_detail_show_real_rows(client: TestClient) -> None:
    ids = seed()
    runs = client.get("/api/v1/runs", headers=AUTH).json()
    assert len(runs) == 3 and {r["repo"] for r in runs} == {"o/a", "o/b"}
    assert [r["repo"] for r in client.get("/api/v1/runs?repo=o/b", headers=AUTH).json()] == ["o/b"]
    assert len(client.get("/api/v1/runs?status=failed", headers=AUTH).json()) == 1
    assert len(client.get("/api/v1/runs?limit=2", headers=AUTH).json()) == 2
    first = next(r for r in runs if r["event_posted"] == "REQUEST_CHANGES")
    assert first["pr_url"] == "https://github.com/o/a/pull/1" and first["changes_dismissed"] is True
    detail = client.get(f"/api/v1/runs/{ids[2]}", headers=AUTH).json()
    assert detail["status"] == "failed" and detail["error"] == "boom"


def test_stats_are_computed_from_the_database(client: TestClient) -> None:
    seed()
    stats = client.get("/api/v1/stats", headers=AUTH).json()
    assert stats["runs_total"] == 3
    assert stats["runs_by_status"] == {"succeeded": 2, "failed": 1}
    assert stats["runs_by_event"] == {"REQUEST_CHANGES": 1, "COMMENT": 1, "none": 1}
    assert stats["findings_total"] == 5 and stats["inline_comments_total"] == 5
    assert stats["deliveries_total"] == 2 and stats["deliveries_by_status"] == {
        "queued": 1,
        "ignored": 1,
    }
    assert stats["last_run_at"] is not None


def test_bad_inputs_are_rejected_cleanly(client: TestClient) -> None:
    assert client.get("/api/v1/runs/not-a-uuid", headers=AUTH).status_code == 422
    assert client.get(f"/api/v1/runs/{uuid4()}", headers=AUTH).status_code == 404
    assert client.get("/api/v1/runs?limit=0", headers=AUTH).status_code == 422
    assert client.get("/api/v1/runs?limit=1000", headers=AUTH).status_code == 422


def test_there_are_no_write_endpoints(client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        for path in ("/api/v1/runs", "/api/v1/stats"):
            assert getattr(client, method)(path, headers=AUTH).status_code in (404, 405)
