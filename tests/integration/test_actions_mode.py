from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lyvern.db import ReviewRun, get_engine
from lyvern.services.actions_mode import seed_prior_reviews

pytestmark = pytest.mark.integration

BOT = "lyvern-bot[bot]"


@pytest.fixture
def db() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_runs, webhook_deliveries CASCADE"))
    yield


def record(review_id: int, state: str, login: str = BOT, sha: str = "a" * 40) -> dict[str, object]:
    return {
        "id": review_id,
        "state": state,
        "user": {"login": login},
        "commit_id": sha,
        "submitted_at": "2026-11-17T10:00:00Z",
    }


def test_only_the_bots_active_reviews_are_rebuilt_from_history(db: None) -> None:
    records = [
        record(1, "CHANGES_REQUESTED"),
        record(2, "APPROVED", sha="b" * 40),
        record(3, "DISMISSED"),  # already dismissed
        record(4, "CHANGES_REQUESTED", login="someone-else"),  # not ours
        record(5, "PENDING"),  # not submitted
        record(6, "COMMENTED", login=BOT.upper()),  # login match ignores case
    ]
    engine = get_engine()
    assert seed_prior_reviews(engine, "o/r", 3, 99, records, BOT) == 3
    with Session(engine) as s:
        rows = {r.github_review_id: r for r in s.scalars(select(ReviewRun))}
    assert set(rows) == {1, 2, 6}
    assert rows[1].event_posted == "REQUEST_CHANGES"
    assert rows[2].event_posted == "APPROVE"
    assert rows[1].changes_dismissed is False
    assert rows[1].status == "succeeded"


def test_two_reviews_of_the_same_commit_do_not_collide(db: None) -> None:
    records = [record(10, "CHANGES_REQUESTED"), record(11, "CHANGES_REQUESTED")]
    assert seed_prior_reviews(get_engine(), "o/r", 3, 99, records, BOT) == 2
