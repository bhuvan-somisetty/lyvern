"""Recognise generated source files.

Style and reliability rules (an empty catch, ``@ts-nocheck``, a debugger statement) are noise on
code that a tool wrote and that nobody edits by hand: the fix would be overwritten the next time
the generator runs. Security rules still run on generated files, because a risky pattern there
is still risky. Found on real code: 17 of 67 findings in a first real-code run were
``@ts-nocheck`` headers in generated Prisma client files.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_DIRS = {"generated", "__generated__", ".generated"}
_NAME_HINTS = (".generated.", ".gen.", "_gen.", ".pb.", "_pb.", ".g.")
_MARKERS = re.compile(
    r"(@generated|auto-?generated|generated (?:file|by|code)|code generated|do not edit)",
    re.IGNORECASE,
)
HEADER_CHARS = 1500  # generators put their notice at the top of the file


def is_generated(path: str, source: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    if any(part.lower() in _DIRS for part in p.parts[:-1]):
        return True
    name = p.name.lower()
    if any(hint in name for hint in _NAME_HINTS):
        return True
    return bool(_MARKERS.search(source[:HEADER_CHARS]))
