from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_SECRET_KEY = "dev-insecure-secret-key-change-me"  # noqa: S105 — rejected in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    expose_docs: bool | None = None  # defaults to True outside production

    database_url: str = "postgresql+asyncpg://alhidaya:alhidaya-dev@localhost:55432/alhidaya"
    db_lock_timeout_ms: int = 5000
    db_statement_timeout_ms: int = 15000
    db_idle_in_transaction_timeout_ms: int = 30000

    # Used as the HMAC pepper for one-time codes. Must be long and random in production.
    secret_key: str = DEV_SECRET_KEY

    app_base_url: str = "http://localhost:5173"
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8000", "http://localhost:8080"]
    )

    cookie_secure: bool = False
    session_ttl_days: int = 30
    session_touch_interval_seconds: int = 300

    code_ttl_minutes: int = 15
    code_max_attempts: int = 5
    code_resend_cooldown_seconds: int = 60
    code_max_per_hour: int = 5
    completion_token_ttl_minutes: int = 30

    login_failures_before_backoff: int = 5
    login_backoff_base_seconds: int = 30
    login_backoff_max_seconds: int = 900

    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    email_backend: Literal["smtp", "console", "memory"] = "console"
    email_from: str = "Al Hidayah Academy <no-reply@alhidayah.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    smtp_use_tls: bool = False
    smtp_timeout_seconds: int = 15

    outbox_worker_enabled: bool = True
    outbox_poll_seconds: float = 5.0
    outbox_max_attempts: int = 8

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random string of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (serve the app over HTTPS)")
        return self

    @property
    def session_cookie_name(self) -> str:
        # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and Path=/.
        return "__Host-alh_session" if self.cookie_secure else "alh_session"

    @property
    def docs_enabled(self) -> bool:
        return self.expose_docs if self.expose_docs is not None else self.env != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
