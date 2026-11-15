"""Task definitions. Real review tasks arrive in later milestones."""

from lyvern.celery_app import celery_app


@celery_app.task(name="lyvern.ping")  # type: ignore[untyped-decorator]  # celery has no type stubs
def ping() -> str:
    return "pong"
