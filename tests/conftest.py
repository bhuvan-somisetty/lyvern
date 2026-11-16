"""Integration tests run against their own database (``<name>_test``), never the dev database.

Several integration tests TRUNCATE tables. Pointing them at the development database would
silently destroy real run history, so the first integration test of a session switches the
whole process to a separate database, creates it if needed, and migrates it to head.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from lyvern.config import Settings, get_settings
from lyvern.db import get_engine

_state: dict[str, str] = {}


def _prepare_test_database() -> str:
    if "url" in _state:
        return _state["url"]
    base = make_url(Settings().database_url.get_secret_value())
    name = base.database or "lyvern"
    test_name = name if name.endswith("_test") else f"{name}_test"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_name}
        ).first()
        if exists is None:
            conn.execute(text(f'CREATE DATABASE "{test_name}"'))
    admin.dispose()
    test_url = base.set(database=test_name).render_as_string(hide_password=False)
    _state["url"] = test_url
    return test_url


@pytest.fixture(autouse=True)
def _isolated_integration_database(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    url = _prepare_test_database()
    monkeypatch.setenv("LYVERN_DATABASE_URL", url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    if "migrated" not in _state:
        command.upgrade(Config("alembic.ini"), "head")
        _state["migrated"] = "yes"
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
