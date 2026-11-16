"""User accounts in the database (used by ``lyvern user ...`` and the login check)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lyvern.auth import (
    DUMMY_HASH,
    hash_password,
    validate_password,
    validate_role,
    validate_username,
    verify_password,
)
from lyvern.db.models import User


class UserError(ValueError):
    pass


def create_user(session: Session, username: str, password: str, role: str) -> User:
    user = User(
        username=validate_username(username),
        password_hash=hash_password(validate_password(password)),
        role=validate_role(role),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise UserError(f"user '{user.username}' already exists") from None
    return user


def get_user(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username.strip().lower()))


def authenticate(session: Session, username: str, password: str) -> User | None:
    """The user if the password is right and the account is enabled; otherwise None.

    A password is always checked (against a dummy hash when the user is unknown), so the answer
    takes about the same time whether or not the username exists.
    """
    user = get_user(session, username)
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    return user if ok and user is not None and not user.disabled else None


def set_password(session: Session, username: str, password: str) -> None:
    user = get_user(session, username)
    if user is None:
        raise UserError(f"no such user '{username}'")
    user.password_hash = hash_password(validate_password(password))
    session.commit()


def set_role(session: Session, username: str, role: str) -> None:
    user = get_user(session, username)
    if user is None:
        raise UserError(f"no such user '{username}'")
    user.role = validate_role(role)
    session.commit()


def set_disabled(session: Session, username: str, disabled: bool) -> None:
    user = get_user(session, username)
    if user is None:
        raise UserError(f"no such user '{username}'")
    user.disabled = disabled
    session.commit()


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)))
