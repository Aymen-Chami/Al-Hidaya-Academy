"""Test harness: a real Postgres database (<name>_test on the configured server), migrated once per
session and truncated before every test. Engine invariants are asserted after every test."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

# Configure the app before anything imports its settings.
os.environ["ENV"] = "test"
os.environ["EMAIL_BACKEND"] = "memory"
os.environ["OUTBOX_WORKER_ENABLED"] = "false"
os.environ["ARGON2_TIME_COST"] = "1"
os.environ["ARGON2_MEMORY_COST"] = "1024"
os.environ["ARGON2_PARALLELISM"] = "1"
os.environ["COOKIE_SECURE"] = "false"

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import clock
from app.core.config import get_settings
from app.db.session import Database, set_db
from app.services.engine.invariants import check_invariants
from app.services.notify.backends import get_backend

TABLES = "audit_events, outbox_emails, email_codes, sessions, waitlist_entries, enrollments, students, classes, users"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def recreate_database(url: str) -> None:
    async def go() -> None:
        target = make_url(url)
        admin = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
        await admin.dispose()

    asyncio.run(go())


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    recreate_database(url)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest_asyncio.fixture(scope="session")
async def db(database_url):
    database = Database(database_url)
    set_db(database)
    yield database
    await database.dispose()
    set_db(None)


@pytest_asyncio.fixture(autouse=True)
async def _clean_database(db):
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    backend = get_backend()
    backend.sent.clear()
    backend.fail_next = 0
    yield
    async with db.sessionmaker() as session:
        violations = await check_invariants(session)
    assert not violations, "Enrollment invariants violated:\n" + "\n".join(violations)


@pytest.fixture(scope="session")
def app():
    from app.main import create_app

    return create_app()


def make_client(app, token: str | None = None) -> AsyncClient:
    cookies = {get_settings().session_cookie_name: token} if token else None
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}, cookies=cookies
    )


@pytest_asyncio.fixture
async def client(app):
    async with make_client(app) as c:
        yield c


@pytest.fixture
def mail():
    """The in-memory email backend (only filled once the outbox worker runs)."""
    return get_backend()


class FrozenClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def frozen_clock(monkeypatch) -> FrozenClock:
    fc = FrozenClock()
    monkeypatch.setattr(clock, "utcnow", lambda: fc.now)
    return fc
