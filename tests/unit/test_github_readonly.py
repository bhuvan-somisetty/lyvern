"""Read-only GitHub client: it must be impossible to write to GitHub through it."""

import base64
import inspect
import re
from typing import Any

import httpx
import pytest

from lyvern.github import client as client_module
from lyvern.github.client import (
    MAX_CONTENT_BYTES,
    GitHubError,
    GitHubRateLimited,
    GitHubReadClient,
)
from lyvern.github.refs import InvalidPullRequestRef, PullRequestRef, parse_pr_reference

REF = PullRequestRef("octo", "repo", 7)


def make_client(handler: Any, **kw: Any) -> tuple[GitHubReadClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[no-any-return]

    return (
        GitHubReadClient(
            "tkn", transport=httpx.MockTransport(wrapped), sleep=lambda _s: None, **kw
        ),
        seen,
    )


# ------------------------------------------------------------ structural read-only guarantee


def test_client_source_contains_no_write_capable_http_calls() -> None:
    source = inspect.getsource(client_module)
    for verb in ("post", "put", "patch", "delete", "request", "send", "stream"):
        assert not re.search(rf"\.{verb}\(", source), f"write-capable call .{verb}( found"
    assert source.count("self._http.get(") == 2  # the single primitive (initial + retry)


def test_client_exposes_no_write_methods() -> None:
    public = [n for n in dir(GitHubReadClient) if not n.startswith("_")]
    # every public method is either close() or a read (get_* / list_*); nothing can write
    assert [n for n in public if n != "close" and not n.startswith(("get_", "list_"))] == []
    forbidden = (
        "post",
        "put",
        "patch",
        "delete",
        "create",
        "submit",
        "merge",
        "approve",
        "dismiss",
    )
    assert [n for n in public if any(n.lower().startswith(w) for w in forbidden)] == []
    assert set(public) == {
        "close",
        "get_pull_request",
        "get_merge_state",
        "list_open_pull_requests",
        "list_changed_files",
        "list_review_comments",
        "get_file_text",
    }


def test_every_request_sent_is_a_get() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=PR_JSON)

    c, seen = make_client(handler)
    c.get_pull_request(REF)
    c.list_changed_files(REF)
    c.get_file_text("octo/repo", "a.py", "abc")
    assert seen and {r.method for r in seen} == {"GET"}


# --------------------------------------------------------------------------------- reads

PR_JSON = {
    "title": "Fix bug",
    "body": None,
    "user": {"login": "alice"},
    "state": "open",
    "draft": False,
    "html_url": "https://github.com/octo/repo/pull/7",
    "base": {"ref": "main", "sha": "b" * 40},
    "head": {"ref": "fix", "sha": "a" * 40, "repo": {"full_name": "alice/repo"}},
    "changed_files": 2,
    "additions": 10,
    "deletions": 3,
}


def test_get_pull_request_maps_fields_including_fork_head_repo() -> None:
    c, seen = make_client(lambda r: httpx.Response(200, json=PR_JSON))
    pr = c.get_pull_request(REF)
    assert (pr.author, pr.head_repo_full_name, pr.body, pr.head_sha) == (
        "alice",
        "alice/repo",
        "",
        "a" * 40,
    )
    assert seen[0].headers["authorization"] == "Bearer tkn"
    assert seen[0].url.path == "/repos/octo/repo/pulls/7"


def test_deleted_fork_head_repo_falls_back_to_base_repo() -> None:
    data = {**PR_JSON, "head": {"ref": "fix", "sha": "a" * 40, "repo": None}}
    c, _ = make_client(lambda r: httpx.Response(200, json=data))
    assert c.get_pull_request(REF).head_repo_full_name == "octo/repo"


def test_file_listing_paginates() -> None:
    def item(i: int) -> dict[str, Any]:
        return {
            "filename": f"f{i}.py",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "patch": "@@ -1 +1 @@\n-a\n+b",
        }

    pages = {"1": [item(i) for i in range(100)], "2": [item(i) for i in range(100, 105)]}
    c, seen = make_client(lambda r: httpx.Response(200, json=pages[r.url.params["page"]]))
    files = c.list_changed_files(REF)
    assert len(files) == 105 and [r.url.params["page"] for r in seen] == ["1", "2"]


def test_retries_transient_errors_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json=PR_JSON)

    c, _ = make_client(handler)
    assert c.get_pull_request(REF).title == "Fix bug" and calls["n"] == 3


def test_persistent_server_error_raises() -> None:
    c, _ = make_client(lambda r: httpx.Response(502, json={"message": "bad gateway"}))
    with pytest.raises(GitHubError) as info:
        c.get_pull_request(REF)
    assert info.value.status == 502


def test_rate_limit_is_reported_with_reset_time() -> None:
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"}
    c, _ = make_client(
        lambda r: httpx.Response(403, headers=headers, json={"message": "rate limit"})
    )
    with pytest.raises(GitHubRateLimited) as info:
        c.get_pull_request(REF)
    assert info.value.reset_epoch == 1893456000


def test_plain_403_is_a_normal_error_not_a_rate_limit() -> None:
    c, _ = make_client(lambda r: httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(GitHubError) as info:
        c.get_pull_request(REF)
    assert not isinstance(info.value, GitHubRateLimited)


def _content(text: bytes, **extra: Any) -> dict[str, Any]:
    return {
        "encoding": "base64",
        "size": len(text),
        "content": base64.b64encode(text).decode(),
        **extra,
    }


def test_get_file_text_decodes_and_encodes_path() -> None:
    c, seen = make_client(lambda r: httpx.Response(200, json=_content("héllo\n".encode())))
    assert c.get_file_text("octo/repo", "src/a b/ü.py", "abc") == "héllo\n"
    assert seen[0].url.params["ref"] == "abc"
    assert "a%20b" in str(seen[0].url)


def test_get_file_text_returns_none_for_missing_binary_large_or_non_base64() -> None:
    c, _ = make_client(lambda r: httpx.Response(404, json={"message": "Not Found"}))
    assert c.get_file_text("o/r", "x", "s") is None
    c2, _ = make_client(lambda r: httpx.Response(200, json=_content(b"\xff\xfe\x00bad")))
    assert c2.get_file_text("o/r", "x", "s") is None
    big = _content(b"x", size=MAX_CONTENT_BYTES + 1)
    c3, _ = make_client(lambda r: httpx.Response(200, json=big))
    assert c3.get_file_text("o/r", "x", "s") is None
    c4, _ = make_client(
        lambda r: httpx.Response(200, json={"encoding": "none", "size": 1, "content": ""})
    )
    assert c4.get_file_text("o/r", "x", "s") is None
    c5, _ = make_client(lambda r: httpx.Response(200, json=[{"name": "a"}]))  # a directory listing
    assert c5.get_file_text("o/r", "x", "s") is None


# ------------------------------------------------------------------------------ references


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "https://github.com/jaegertracing/jaeger-ui/pull/123",
            ("jaegertracing", "jaeger-ui", 123),
        ),
        ("https://github.com/o/r/pull/9/files", ("o", "r", 9)),
        ("http://www.github.com/o/r/pull/9?diff=split#x", ("o", "r", 9)),
        ("  joinmarket-webui/jam#1618  ", ("joinmarket-webui", "jam", 1618)),
        ("a.b/c_d-e#5", ("a.b", "c_d-e", 5)),
    ],
)
def test_parse_pr_reference_accepts(text: str, expected: tuple[str, str, int]) -> None:
    ref = parse_pr_reference(text)
    assert (ref.owner, ref.repo, ref.number) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "o/r",
        "o/r#",
        "o/r#0",
        "https://gitlab.com/o/r/pull/1",
        "https://github.com/o/r/issues/1",
        "o/r#1; rm -rf /",
        "https://github.com/o/r/pull/x",
    ],
)
def test_parse_pr_reference_rejects(text: str) -> None:
    with pytest.raises(InvalidPullRequestRef):
        parse_pr_reference(text)
