"""Celery entry module: configures logging and exposes the shared Celery app."""

from printel.celery_app import celery_app
from printel.config import get_settings
from printel.logging import configure_logging

configure_logging(get_settings().log_level)
app = celery_app

__all__ = ["app"]
