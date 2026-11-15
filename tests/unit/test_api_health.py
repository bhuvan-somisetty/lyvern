from unittest.mock import patch

from fastapi.testclient import TestClient

from lyvern_api.main import create_app


def test_healthz_and_request_id() -> None:
    client = TestClient(create_app())
    r = client.get("/healthz", headers={"x-request-id": "abc"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"] == "abc"


def test_readyz_503_when_dependency_down() -> None:
    with (
        patch("lyvern_api.main.check_db", return_value=True),
        patch("lyvern_api.main.check_redis", return_value=False),
    ):
        r = TestClient(create_app()).get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"] == {"database": True, "redis": False}


def test_readyz_200_when_all_up() -> None:
    with (
        patch("lyvern_api.main.check_db", return_value=True),
        patch("lyvern_api.main.check_redis", return_value=True),
    ):
        r = TestClient(create_app()).get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
