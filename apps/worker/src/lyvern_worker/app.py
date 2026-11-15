"""Celery entry module: configures logging and exposes the shared Celery app."""

from lyvern.celery_app import celery_app
from lyvern.config import get_settings
from lyvern.logging import configure_logging

configure_logging(get_settings().log_level)
app = celery_app

__all__ = ["app"]
