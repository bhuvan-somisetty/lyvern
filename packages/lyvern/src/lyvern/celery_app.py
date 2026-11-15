"""Celery application and Redis connectivity check.

The database is the source of truth for review jobs; the queue only carries work.
"""

import redis
from celery import Celery

from lyvern.config import get_settings


def _make_celery() -> Celery:
    redis_url = get_settings().redis_url.get_secret_value()
    app = Celery("lyvern", broker=redis_url, backend=redis_url, include=["lyvern.tasks"])
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = _make_celery()


def check_redis() -> bool:
    """Return True if Redis answers PING. Never raises."""
    try:
        client = redis.Redis.from_url(
            get_settings().redis_url.get_secret_value(), socket_connect_timeout=2
        )
        return bool(client.ping())
    except Exception:
        return False
