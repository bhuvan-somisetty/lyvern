from __future__ import annotations

from lyvern.services.actions_mode import parse_event


def event(action: str = "opened", draft: bool = False) -> dict[str, object]:
    return {
        "action": action,
        "repository": {"full_name": "o/r"},
        "pull_request": {"number": 7, "draft": draft, "head": {"sha": "a" * 40}},
    }


def test_reviewable_events_give_repo_number_and_head() -> None:
    for action in ("opened", "synchronize", "reopened", "ready_for_review"):
        assert parse_event(event(action)) == ("o/r", 7, "a" * 40)


def test_other_actions_and_drafts_are_ignored() -> None:
    assert parse_event(event("closed")) is None
    assert parse_event(event("labeled")) is None
    assert parse_event(event(draft=True)) is None


def test_malformed_payloads_are_ignored() -> None:
    assert parse_event({}) is None
    assert parse_event({"action": "opened", "pull_request": {}}) is None
