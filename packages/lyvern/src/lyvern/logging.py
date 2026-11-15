"""Structured JSON logging with a correlation id and secret scrubbing."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|private[_-]?key|authorization)", re.I
)
_SENSITIVE_VALUE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def scrub(value: Any, key: str = "") -> Any:
    """Redact values stored under sensitive keys and token-shaped strings."""
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub("[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _SENSITIVE_VALUE.sub("[REDACTED]", record.getMessage()),
            "correlation_id": correlation_id.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = scrub(value, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
