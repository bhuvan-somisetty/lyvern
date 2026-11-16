"""Dashboard account helpers: hashing, validation, roles."""

import pytest

from lyvern.auth import (
    DUMMY_HASH,
    MIN_PASSWORD_LENGTH,
    InvalidCredentialsFormat,
    can_label,
    hash_password,
    validate_password,
    validate_role,
    validate_username,
    verify_password,
)


def test_a_password_verifies_only_when_it_is_exactly_right() -> None:
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored)
    for wrong in ("correct horse batterY", "", " correct horse battery", "correct horse battery "):
        assert not verify_password(wrong, stored)


def test_every_hash_has_its_own_salt_and_never_contains_the_password() -> None:
    a, b = hash_password("same password here"), hash_password("same password here")
    assert (
        a != b
        and verify_password("same password here", a)
        and verify_password("same password here", b)
    )
    assert "same password here" not in a and a.startswith("scrypt$16384$8$1$")


def test_malformed_stored_values_fail_instead_of_raising() -> None:
    for broken in ("", "x", "scrypt$1$2$3", "md5$16384$8$1$AAAA$AAAA", "scrypt$a$b$c$d$e",
                   "scrypt$16384$8$1$!!!$!!!", hash_password("abcdefghij")[:-6]):  # fmt: skip
        assert verify_password("abcdefghij", broken) is False


def test_the_dummy_hash_is_a_real_hash_that_matches_nothing_guessable() -> None:
    assert DUMMY_HASH.startswith("scrypt$") and not verify_password("password", DUMMY_HASH)


def test_usernames_are_normalised_and_restricted() -> None:
    assert validate_username("  Alice.Smith ") == "alice.smith"
    for bad in ("", "a", "-bad", "has space", "UPPER!", "x" * 33, "tab\tname", "é-user", "a/b"):
        with pytest.raises(InvalidCredentialsFormat):
            validate_username(bad)


def test_passwords_must_be_long_enough_and_not_absurd() -> None:
    assert validate_password("x" * MIN_PASSWORD_LENGTH)
    with pytest.raises(InvalidCredentialsFormat):
        validate_password("x" * (MIN_PASSWORD_LENGTH - 1))
    with pytest.raises(InvalidCredentialsFormat):
        validate_password("x" * 257)


def test_roles_and_who_may_label() -> None:
    for role in ("viewer", "reviewer", "admin"):
        assert validate_role(role) == role
    with pytest.raises(InvalidCredentialsFormat):
        validate_role("owner")
    assert can_label("reviewer") and can_label("admin")
    assert not can_label("viewer") and not can_label("") and not can_label("root")
