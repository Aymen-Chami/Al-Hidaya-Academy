import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_refuses_weak_secret_or_insecure_cookie():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(env="production", secret_key="too-short", cookie_secure=True)
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(env="production", secret_key="x" * 40, cookie_secure=False)


def test_production_defaults():
    s = Settings(env="production", secret_key="x" * 40, cookie_secure=True)
    assert s.session_cookie_name == "__Host-alh_session"
    assert s.docs_enabled is False


def test_allowed_origins_from_comma_separated_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://signup.example.org, http://localhost:5173/")
    assert Settings().allowed_origins == ["https://signup.example.org", "http://localhost:5173"]
