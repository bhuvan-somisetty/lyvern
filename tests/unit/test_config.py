import pytest

from lyvern.config import Settings


def test_defaults_do_not_leak_secrets_in_repr() -> None:
    s = Settings()
    assert "lyvern:lyvern@" not in repr(s)
    assert s.product_name == "Lyvern"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LYVERN_ENVIRONMENT", "test")
    monkeypatch.setenv("LYVERN_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.environment == "test"
    assert s.log_level == "DEBUG"


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LYVERN_ENVIRONMENT", "staging")
    with pytest.raises(ValueError):
        Settings()
