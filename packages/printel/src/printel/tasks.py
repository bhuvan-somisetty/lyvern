"""Task definitions. Real review tasks arrive in later milestones."""

from printel.celery_app import celery_app


@celery_app.task(name="printel.ping")  # type: ignore[untyped-decorator]  # celery has no type stubs
def ping() -> str:
    return "pong"
