"""Remove secrets from text before it leaves the machine."""

from __future__ import annotations

import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"AQ\.[A-Za-z0-9_-]{30,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
)
_ASSIGNED_SECRET = re.compile(
    r"""((?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)"""
    r"""['"]?\s*[:=]\s*['"])([^'"\n]{6,})(['"])""",
    re.I,
)
REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> tuple[str, int]:
    """Return the text with secrets replaced and how many replacements were made."""
    count = 0
    for pattern in _PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        count += n
    text, n = _ASSIGNED_SECRET.subn(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", text)
    return text, count + n
