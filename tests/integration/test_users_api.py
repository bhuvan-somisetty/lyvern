"""User accounts against the real (test) database: service, login endpoint, CLI, verdict author."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from lyvern import cli
from lyvern.config import get_settings
from lyvern.db import FindingRecord, ReviewRun, User, get_engine
from lyvern.services import users
from lyvern_api import dashboard
from lyvern_api import main as api_main

pytestmark = pytest.mark.integration

TOKEN = "dashboard-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PASSWORD = "a long enough password"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LYVERN_API_TOKEN", TOKEN)
    get_settings.cache_clear()
    dashboard._ATTEMPTS.clear()
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries, users CASCADE"))
    yield TestClient(api_main.create_app())
    get_settings.cache_clear()


def make(username: str = "alice", role: str = "reviewer", password: str = PASSWORD) -> None:
    with Session(get_engine()) as s:
        users.create_user(s, username, password, role)


def test_create_authenticate_and_the_stored_hash(client: TestClient) -> None:
    make("Alice", "admin")
    with Session(get_engine()) as s:
        row = s.query(User).one()
        assert row.username == "alice" and row.role == "admin" and PASSWORD not in row.password_hash
        assert users.authenticate(s, "ALICE", PASSWORD) is not None
        assert users.authenticate(s, "alice", PASSWORD + "x") is None
        assert users.authenticate(s, "nobody", PASSWORD) is None
        with pytest.raises(users.UserError, match="already exists"):
            users.create_user(s, "alice", PASSWORD, "viewer")


def test_disabled_accounts_cannot_sign_in_and_can_be_re_enabled(client: TestClient) -> None:
    make()
    with Session(get_engine()) as s:
        users.set_disabled(s, "alice", True)
        assert users.authenticate(s, "alice", PASSWORD) is None
        users.set_disabled(s, "alice", False)
        assert users.authenticate(s, "alice", PASSWORD) is not None
        users.set_role(s, "alice", "viewer")
        users.set_password(s, "alice", "another long password")
        assert users.authenticate(s, "alice", PASSWORD) is None
        found = users.authenticate(s, "alice", "another long password")
        assert found is not None and found.role == "viewer"
        for call in (users.set_disabled, users.set_role, users.set_password):
            with pytest.raises(users.UserError):
                call(s, "ghost", "viewer" if call is users.set_role else True)  # type: ignore[arg-type]


def test_login_endpoint_needs_the_token_and_never_says_which_part_was_wrong(
    client: TestClient,
) -> None:
    make("bob", "viewer")
    body = {"username": "bob", "password": PASSWORD}
    assert client.post("/api/v1/auth/verify", json=body).status_code == 401  # no API token
    ok = client.post("/api/v1/auth/verify", headers=AUTH, json=body)
    assert ok.status_code == 200 and ok.json() == {
        "username": "bob",
        "role": "viewer",
        "can_label": False,
    }
    wrong_pw = client.post(
        "/api/v1/auth/verify", headers=AUTH, json={**body, "password": "nope nope nope"}
    )
    wrong_user = client.post("/api/v1/auth/verify", headers=AUTH, json={**body, "username": "zed"})
    assert wrong_pw.status_code == wrong_user.status_code == 401
    assert wrong_pw.json() == wrong_user.json()  # identical answers
    assert PASSWORD not in wrong_pw.text and "hash" not in ok.text


def test_repeated_failures_are_slowed_down_per_username(client: TestClient) -> None:
    make("carol", "reviewer")
    bad = {"username": "carol", "password": "wrong password!"}
    codes = [
        client.post("/api/v1/auth/verify", headers=AUTH, json=bad).status_code for _ in range(9)
    ]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    good = client.post(
        "/api/v1/auth/verify", headers=AUTH, json={"username": "carol", "password": PASSWORD}
    )
    assert good.status_code == 429  # even the right password waits out the window
    other = make
    other("dave", "viewer")
    assert (
        client.post(
            "/api/v1/auth/verify", headers=AUTH, json={"username": "dave", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_a_verdict_records_who_gave_it(client: TestClient) -> None:
    with Session(get_engine()) as s:
        run = ReviewRun(
            id=uuid4(), repo_full_name="o/a", pr_number=1, head_sha="a" * 40, installation_id=1,
            trigger_delivery_id="d", status="succeeded",
        )  # fmt: skip
        s.add(run)
        s.flush()
        finding = FindingRecord(
            id=uuid4(), run_id=run.id, fingerprint="fp", file_path="a.py", line_start=1,
            line_end=1, severity="high", category="bug", origin="static_analysis",
            detection_source="ruff:F821", title="t", confidence=0.9,
        )  # fmt: skip
        s.add(finding)
        s.commit()
        fid: UUID = finding.id
    r = client.put(
        f"/api/v1/findings/{fid}/feedback",
        headers=AUTH,
        json={"verdict": "true_positive", "reviewer": "alice"},
    )
    assert r.status_code == 200
    with Session(get_engine()) as s:
        from lyvern.db import FindingFeedback

        assert s.query(FindingFeedback).one().reviewer == "alice"
    client.put(
        f"/api/v1/findings/{fid}/feedback",
        headers=AUTH,
        json={"verdict": "false_positive", "reviewer": "bob"},
    )
    with Session(get_engine()) as s:
        row = s.query(FindingFeedback).one()
        assert (row.verdict, row.reviewer) == ("false_positive", "bob")


def test_the_user_cli_creates_lists_changes_and_validates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LYVERN_NEW_PASSWORD", PASSWORD)
    assert cli.main(["user", "add", "erin", "--role", "reviewer"]) == 0
    assert "created erin (reviewer)" in capsys.readouterr().out
    assert cli.main(["user", "add", "erin"]) == 2 and "already exists" in capsys.readouterr().err
    assert cli.main(["user", "add", "Bad Name"]) == 2 and "username" in capsys.readouterr().err
    monkeypatch.setenv("LYVERN_NEW_PASSWORD", "short")
    assert cli.main(["user", "add", "frank"]) == 2 and "at least" in capsys.readouterr().err
    assert cli.main(["user", "set-role", "erin", "admin"]) == 0
    assert cli.main(["user", "disable", "erin"]) == 0
    capsys.readouterr()
    assert cli.main(["user", "list"]) == 0
    out = capsys.readouterr().out
    assert "erin\tadmin (disabled)" in out and PASSWORD not in out and "scrypt" not in out
    assert cli.main(["user", "enable", "erin"]) == 0
    assert cli.main(["user", "set-role", "ghost", "viewer"]) == 2
