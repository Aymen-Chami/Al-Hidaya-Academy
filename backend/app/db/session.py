from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings


class Database:
    def __init__(self, url: str) -> None:
        s = get_settings()
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "application_name": "alhidaya-api",
                    # lock_timeout also bounds the wait on the enrollment-engine advisory lock.
                    "lock_timeout": str(s.db_lock_timeout_ms),
                    "statement_timeout": str(s.db_statement_timeout_ms),
                    "idle_in_transaction_session_timeout": str(s.db_idle_in_transaction_timeout_ms),
                }
            },
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(get_settings().database_url)
    return _db


def set_db(db: Database | None) -> None:
    """Swap the process-wide database (used by tests and the CLI)."""
    global _db
    _db = db
