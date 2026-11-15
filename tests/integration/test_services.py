"""Needs running services: docker compose up -d db redis, then `alembic upgrade head`."""

import pytest
from sqlalchemy import text

from printel.celery_app import celery_app, check_redis
from printel.db import check_db, get_engine
from printel.tasks import ping

pytestmark = pytest.mark.integration


def test_database_and_redis_reachable() -> None:
    assert check_db()
    assert check_redis()


def test_pgvector_extension_present_after_migration() -> None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).first()
    assert row is not None


def test_task_is_registered_and_runs_eagerly() -> None:
    assert "printel.ping" in celery_app.tasks
    assert ping.apply().get() == "pong"


def test_worker_round_trip_through_redis() -> None:
    """Needs the worker container: docker compose up -d. Fails (not skips) if no worker answers."""
    assert ping.delay().get(timeout=60) == "pong"


def test_redis_is_the_project_instance() -> None:
    """Guard against another Redis (e.g. in WSL) answering on the same port."""
    import redis

    from printel.config import get_settings

    client = redis.Redis.from_url(get_settings().redis_url.get_secret_value())
    assert str(client.info("server")["redis_version"]).startswith("7.")
