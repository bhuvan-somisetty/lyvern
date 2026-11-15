import json
import logging

from lyvern.logging import JsonFormatter, correlation_id, scrub


def _format(msg: str, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_sensitive_keys_are_redacted() -> None:
    out = _format("hello", api_key="abc123", webhook_secret="s3cret", repo="o/r")
    assert out["api_key"] == "[REDACTED]"
    assert out["webhook_secret"] == "[REDACTED]"
    assert out["repo"] == "o/r"


def test_token_shaped_values_are_redacted_in_message() -> None:
    token = "ghp_" + "a" * 36
    out = _format(f"auth failed for {token}")
    assert token not in json.dumps(out)


def test_nested_values_are_scrubbed() -> None:
    assert scrub({"headers": {"Authorization": "Bearer x"}, "n": 1}) == {
        "headers": {"Authorization": "[REDACTED]"},
        "n": 1,
    }


def test_correlation_id_is_included() -> None:
    token = correlation_id.set("req-1")
    try:
        assert _format("x")["correlation_id"] == "req-1"
    finally:
        correlation_id.reset(token)
