"""Webhook verification, App authentication and the guarded publisher (mock transports only)."""

import json
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from lyvern.engine.contracts import ReviewEvent
from lyvern.engine.render import MARKER_PREFIX
from lyvern.github.app_auth import AppAuth, AppAuthError
from lyvern.github.publisher import (
    GitHubPublisher,
    PublishError,
    ReviewComment,
    WriteGuard,
    WriteNotAllowed,
)
from lyvern.github.webhook import (
    InvalidWebhook,
    compute_signature,
    parse_pull_request_event,
    verify_signature,
)

SECRET = "test-secret"
REPO = "bhuvan-somisetty/lyvern-sandbox"

# ----------------------------------------------------------------------------- webhook


def test_signature_accepts_only_the_exact_hmac_of_the_raw_body() -> None:
    body = b'{"action":"opened"}'
    good = compute_signature(SECRET, body)
    assert verify_signature(SECRET, body, good)
    assert not verify_signature(SECRET, body + b" ", good)  # body tampered
    assert not verify_signature("other", body, good)  # wrong secret
    assert not verify_signature(SECRET, body, None)
    assert not verify_signature(SECRET, body, "")
    assert not verify_signature(SECRET, body, good.replace("sha256=", "sha1="))
    assert not verify_signature(SECRET, body, good.upper())  # constant-time exact compare
    assert not verify_signature("", body, good)  # an empty secret never verifies


def pr_payload(**over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "action": "opened",
        "installation": {"id": 99},
        "repository": {"full_name": REPO},
        "sender": {"login": "bhuvan-somisetty"},
        "pull_request": {
            "number": 3,
            "draft": False,
            "user": {"login": "bhuvan-somisetty"},
            "head": {"sha": "a" * 40, "ref": "feature"},
            "base": {"sha": "b" * 40, "ref": "main"},
        },
    }
    data.update(over)
    return data


def headers(event: str = "pull_request", delivery: str | None = "d-1") -> dict[str, str]:
    out = {"X-GitHub-Event": event}
    if delivery:
        out["X-GitHub-Delivery"] = delivery
    return out


def test_parse_pull_request_event_extracts_only_needed_fields() -> None:
    ev = parse_pull_request_event(headers(), json.dumps(pr_payload()).encode())
    assert ev is not None
    assert (ev.delivery_id, ev.action, ev.installation_id, ev.repo_full_name) == (
        "d-1",
        "opened",
        99,
        REPO,
    )
    assert (ev.pr_number, ev.head_sha, ev.draft, ev.should_review) == (3, "a" * 40, False, True)


def test_other_events_and_non_review_actions() -> None:
    assert parse_pull_request_event(headers("push"), b"{}") is None
    assert parse_pull_request_event(headers("ping"), b"{}") is None
    closed = parse_pull_request_event(headers(), json.dumps(pr_payload(action="closed")).encode())
    assert closed is not None and not closed.should_review
    for action in ("opened", "synchronize", "reopened", "ready_for_review"):
        ev = parse_pull_request_event(headers(), json.dumps(pr_payload(action=action)).encode())
        assert ev is not None and ev.should_review


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"action":"opened"}', b"[]", b"null"])
def test_malformed_pull_request_payloads_are_rejected(body: bytes) -> None:
    with pytest.raises(InvalidWebhook):
        parse_pull_request_event(headers(), body)


def test_missing_delivery_id_is_rejected() -> None:
    with pytest.raises(InvalidWebhook):
        parse_pull_request_event(headers(delivery=None), json.dumps(pr_payload()).encode())


# ----------------------------------------------------------------------------- app auth


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


def test_app_jwt_is_rs256_short_lived_and_names_the_app(keypair: tuple[str, str]) -> None:
    private, public = keypair
    auth = AppAuth("12345", private, clock=lambda: 1_000_000.0)
    claims = jwt.decode(auth.app_jwt(), public, algorithms=["RS256"], options={"verify_exp": False})
    assert claims["iss"] == "12345"
    assert claims["exp"] - claims["iat"] <= 600  # GitHub allows at most 10 minutes


def test_installation_token_is_cached_and_refreshed_before_expiry(keypair: tuple[str, str]) -> None:
    calls = {"n": 0}
    now = {"t": 1_000_000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.method == "POST" and request.url.path == "/app/installations/7/access_tokens"
        assert request.headers["authorization"].startswith("Bearer ey")  # app JWT
        return httpx.Response(
            201, json={"token": f"ghs_token_{calls['n']}", "expires_at": "2001-09-09T01:46:40Z"}
        )

    # expires_at 2001-09-09T01:46:40Z == epoch 1_000_000_000
    auth = AppAuth("1", keypair[0], transport=httpx.MockTransport(handler), clock=lambda: now["t"])
    now["t"] = 1_000_000_000.0 - 3600
    assert auth.installation_token(7) == "ghs_token_1"
    assert auth.installation_token(7) == "ghs_token_1" and calls["n"] == 1  # cached
    now["t"] = 1_000_000_000.0 - 60  # inside the refresh margin
    assert auth.installation_token(7) == "ghs_token_2" and calls["n"] == 2


def test_failed_token_exchange_raises_without_leaking_details(keypair: tuple[str, str]) -> None:
    auth = AppAuth("1", keypair[0], transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(AppAuthError) as info:
        auth.installation_token(1)
    assert "401" in str(info.value) and "BEGIN" not in str(info.value)


def test_app_auth_requires_id_and_key() -> None:
    with pytest.raises(AppAuthError):
        AppAuth("", "key")
    with pytest.raises(AppAuthError):
        AppAuth("1", "")


# ------------------------------------------------------------------------------ publisher


class Recorder:
    def __init__(
        self, responses: list[httpx.Response], existing: list[dict[str, Any]] | None = None
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = list(responses)
        self._existing = existing or []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=self._existing)
        return self._responses.pop(0)

    @property
    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


def make_publisher(rec: Recorder, allowed: str = REPO) -> GitHubPublisher:
    return GitHubPublisher(
        WriteGuard.from_setting(allowed), lambda: "tok", transport=httpx.MockTransport(rec)
    )


def ok(review_id: int = 11) -> httpx.Response:
    return httpx.Response(200, json={"id": review_id})


def c(line: int, body: str = "x", start: int | None = None) -> ReviewComment:
    return ReviewComment("a.py", line, body, start_line=start)


def test_write_guard_blocks_other_repositories_before_any_network_call() -> None:
    rec = Recorder([ok()])
    pub = make_publisher(rec)
    for repo in (
        "jaegertracing/jaeger-ui",
        "joinmarket-webui/jam",
        "bhuvan-somisetty/lyvern",
        "x/y",
    ):
        with pytest.raises(WriteNotAllowed):
            pub.publish_review(repo, 1, "a" * 40, ReviewEvent.COMMENT, "b", [c(1)])
    assert rec.requests == []  # not even a GET happened
    with pytest.raises(WriteNotAllowed):
        pub.existing_fingerprints("jaegertracing/jaeger-ui", 1)
    assert rec.requests == []


def test_empty_or_blank_allowlist_allows_nothing_and_matching_is_case_insensitive() -> None:
    assert_blocked = make_publisher(Recorder([]), allowed="")
    with pytest.raises(WriteNotAllowed):
        assert_blocked.publish_review(REPO, 1, "a", ReviewEvent.COMMENT, "b", [])
    rec = Recorder([ok()])
    make_publisher(rec, allowed=" Bhuvan-Somisetty/LYVERN-sandbox , other/repo ").publish_review(
        REPO, 1, "a" * 40, ReviewEvent.COMMENT, "b", []
    )
    assert len(rec.posts) == 1


def test_review_payload_uses_explicit_event_commit_and_line_side() -> None:
    rec = Recorder([ok(42)])
    result = make_publisher(rec).publish_review(
        REPO,
        3,
        "c" * 40,
        ReviewEvent.REQUEST_CHANGES,
        "summary",
        [c(5, "one"), c(9, "two", start=7)],
    )
    (post,) = rec.posts
    assert post.url.path == f"/repos/{REPO}/pulls/3/reviews"
    payload = json.loads(post.content)
    assert payload["event"] == "REQUEST_CHANGES" and payload["commit_id"] == "c" * 40
    assert payload["comments"][0] == {"path": "a.py", "line": 5, "side": "RIGHT", "body": "one"}
    assert (
        payload["comments"][1]["start_line"] == 7
        and payload["comments"][1]["start_side"] == "RIGHT"
    )
    assert (result.review_id, result.event_posted, result.inline_posted) == (
        42,
        ReviewEvent.REQUEST_CHANGES,
        2,
    )
    assert post.headers["authorization"] == "Bearer tok"


def test_comments_already_posted_by_an_earlier_run_are_skipped() -> None:
    old = f"earlier\n<!-- {MARKER_PREFIX}abc123 -->"
    rec = Recorder([ok()], existing=[{"body": old}])
    dup = c(5, f"same issue\n<!-- {MARKER_PREFIX}abc123 -->")
    new = c(6, f"new issue\n<!-- {MARKER_PREFIX}def456 -->")
    result = make_publisher(rec).publish_review(
        REPO, 3, "a" * 40, ReviewEvent.COMMENT, "s", [dup, new]
    )
    payload = json.loads(rec.posts[0].content)
    assert [x["line"] for x in payload["comments"]] == [6]
    assert result.inline_skipped_duplicates == 1 and result.inline_posted == 1


def test_refused_approval_is_downgraded_to_comment_and_says_so() -> None:
    refused = httpx.Response(
        422,
        json={
            "message": "Unprocessable Entity",
            "errors": ["Can not approve your own pull request"],
        },
    )
    rec = Recorder([refused, ok(5)])
    result = make_publisher(rec).publish_review(
        REPO, 3, "a" * 40, ReviewEvent.APPROVE, "body", [c(5)]
    )
    first, second = (json.loads(r.content) for r in rec.posts)
    assert first["event"] == "APPROVE" and second["event"] == "COMMENT"
    assert "comment only" in second["body"] and "downgraded" in " ".join(result.notes)
    assert (
        result.event_requested == ReviewEvent.APPROVE and result.event_posted == ReviewEvent.COMMENT
    )


def test_rejected_inline_location_moves_comments_into_the_body_not_lost() -> None:
    bad = httpx.Response(
        422, json={"message": "Unprocessable Entity", "errors": ["line must be part of the diff"]}
    )
    rec = Recorder([bad, ok(8)])
    result = make_publisher(rec).publish_review(
        REPO, 3, "a" * 40, ReviewEvent.COMMENT, "body", [c(5, "finding text")]
    )
    second = json.loads(rec.posts[1].content)
    assert "comments" not in second and "finding text" in second["body"]
    assert result.inline_moved_to_body == 1 and result.inline_posted == 0


def test_other_failures_raise_and_are_never_reported_as_published() -> None:
    for status in (401, 403, 404, 500):
        rec = Recorder([httpx.Response(status)])
        with pytest.raises(PublishError):
            make_publisher(rec).publish_review(REPO, 3, "a" * 40, ReviewEvent.COMMENT, "b", [])
    rec = Recorder([httpx.Response(422, json={"message": "nope"})])
    with pytest.raises(PublishError):
        make_publisher(rec).publish_review(REPO, 3, "a" * 40, ReviewEvent.COMMENT, "b", [])


def test_listing_existing_comments_paginates() -> None:
    pages = {
        "1": [{"body": f"<!-- {MARKER_PREFIX}aa{i:02d} -->"} for i in range(100)],
        "2": [{"body": f"<!-- {MARKER_PREFIX}bb01 -->"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params["page"]])

    pub = GitHubPublisher(WriteGuard([REPO]), lambda: "t", transport=httpx.MockTransport(handler))
    found = pub.existing_fingerprints(REPO, 1)
    assert len(found) == 101 and "bb01" in found
