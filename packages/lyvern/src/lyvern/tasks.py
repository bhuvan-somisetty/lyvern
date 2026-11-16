"""Celery task definitions."""

from uuid import UUID

from lyvern.celery_app import celery_app


@celery_app.task(name="lyvern.ping")  # type: ignore[untyped-decorator]  # celery has no type stubs
def ping() -> str:
    return "pong"


@celery_app.task(name="lyvern.review.run")  # type: ignore[untyped-decorator]
def run_review(run_id: str) -> None:
    """Run the queued review identified by ``run_id`` (see ``services.review_job``)."""
    from lyvern.services.review_job import execute_review_from_settings

    execute_review_from_settings(UUID(run_id))


@celery_app.task(name="lyvern.conflicts.check")  # type: ignore[untyped-decorator]
def check_conflicts(repo: str, installation_id: int, branch: str) -> int:
    """Re-check open pull requests that target ``branch`` after a push to it."""
    from lyvern.services.conflict_check import check_from_settings

    return check_from_settings(repo, installation_id, branch)
