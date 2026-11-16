"""Dashboard user accounts: password hashing, validation and roles.

Passwords are hashed with scrypt (memory-hard, in the standard library) with a random salt per
user, and compared in constant time. A password is never stored, logged or returned.

Roles: ``viewer`` can look at reviews, ``reviewer`` can also mark findings right or wrong,
``admin`` can do that too (user management is done on the server with ``lyvern user ...``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

ROLES = ("viewer", "reviewer", "admin")
LABELLING_ROLES = ("reviewer", "admin")
MIN_PASSWORD_LENGTH = 10
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")

_N, _R, _P = 2**14, 8, 1
_SCHEME = "scrypt"


class InvalidCredentialsFormat(ValueError):
    pass


def validate_username(username: str) -> str:
    cleaned = username.strip().lower()
    if not USERNAME_RE.fullmatch(cleaned):
        raise InvalidCredentialsFormat(
            "username must be 2-32 characters: lowercase letters, digits, '.', '_' or '-'"
        )
    return cleaned


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidCredentialsFormat(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password) > 256:
        raise InvalidCredentialsFormat("password must be at most 256 characters")
    return password


def validate_role(role: str) -> str:
    if role not in ROLES:
        raise InvalidCredentialsFormat(f"role must be one of {', '.join(ROLES)}")
    return role


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * 1024 * 1024
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{_SCHEME}${_N}${_R}${_P}${_b64(salt)}${_b64(_derive(password, salt, _N, _R, _P))}"


def verify_password(password: str, stored: str) -> bool:
    """True only for the exact password. Malformed stored values never raise: they fail."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != _SCHEME:
            return False
        expected = base64.b64decode(digest, validate=True)
        actual = _derive(password, base64.b64decode(salt, validate=True), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Used when the username does not exist, so a wrong user costs the same time as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def can_label(role: str) -> bool:
    return role in LABELLING_ROLES
