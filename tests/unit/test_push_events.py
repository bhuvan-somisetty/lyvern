"""Push-event parsing and the read client's open-pull-request listing."""

import json
from typing import Any

import httpx
import pytest

from lyvern.github.client import GitHubReadClient
from lyvern.github.webhook import InvalidWebhook, parse_push_event

H = {"X-GitHub-Event": "push", "X-GitHub-Delivery": "d1"}


def body(**over: Any) -> bytes:
    data: dict[str, Any] = {
        "ref": "refs/heads/main",
        "deleted": False,
        "installation": {"id": 5},
        "repository": {"full_name": "octo/repo"},
        "sender": {"login": "alice"},
    }
    data.update(over)
    return json.dumps(data).encode()


def test_branch_push_is_parsed() -> None:
    e = parse_push_event(H, body())
    assert e is not None and e.branch == "main" and e.repo_full_name == "octo/repo"
    assert e.installation_id == 5 and e.should_check
    nested = parse_push_event(H, body(ref="refs/heads/feature/x"))
    assert nested is not None and nested.branch == "feature/x"


def test_tags_other_events_and_deleted_branches_are_not_checked() -> None:
    assert parse_push_event(H, body(ref="refs/tags/v1")) is None
    assert parse_push_event({**H, "X-GitHub-Event": "ping"}, b"{}") is None
    deleted = parse_push_event(H, body(deleted=True))
    assert deleted is not None and not deleted.should_check


def test_malformed_pushes_are_rejected() -> None:
    with pytest.raises(InvalidWebhook):
        parse_push_event(H, b"not json")
    with pytest.raises(InvalidWebhook):
        parse_push_event(H, body(installation=None))
    with pytest.raises(InvalidWebhook):
        parse_push_event({"X-GitHub-Event": "push"}, body())


def item(number: int, base: str = "main") -> dict[str, Any]:
    return {
        "number": number,
        "title": "t",
        "body": None,
        "user": {"login": "a"},
        "state": "open",
        "draft": False,
        "html_url": f"https://github.com/o/r/pull/{number}",
        "head": {"ref": f"f{number}", "sha": "a" * 40, "repo": {"full_name": "o/r"}},
        "base": {"ref": base, "sha": "b" * 40},
    }


def test_listing_open_pull_requests_is_filtered_paged_and_bounded() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(200, json=[item(page * 100 + i) for i in range(50)])

    client = GitHubReadClient("t", transport=httpx.MockTransport(handler))
    got = client.list_open_pull_requests("o", "r", "main", limit=120)
    assert len(got) == 120 and len(seen) == 3
    assert all(r.method == "GET" for r in seen)
    assert seen[0].url.params["base"] == "main" and seen[0].url.params["state"] == "open"

    one = GitHubReadClient(
        "t", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[item(1)]))
    )
    assert [p.number for p in one.list_open_pull_requests("o", "r", "main")] == [1]
