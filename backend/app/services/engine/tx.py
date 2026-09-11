"""The enrollment engine's transaction: one global advisory lock serializes every mutation.

Why a single global lock: at Sunday-school scale writes are rare and fast, and it makes every
check-then-write (last seat, one class per period, waitlist cascades that touch several classes)
race-free and deadlock-free. The DB's unique indexes remain as a backstop.

Rules for code running inside an EngineTx:
  * read with Core selects (never rely on ORM objects loaded before the lock),
  * write with explicit Core statements in a deliberate order (delete before insert),
  * never do network I/O (emails are queued to the outbox and sent after commit).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.db.session import get_db
from app.models import User, audit_t, outbox_t
from app.models.enums import Role
from app.services.notify.outbox import outbox_row, wake_outbox

ENGINE_LOCK_KEY = 4_172_026_001


@dataclass(frozen=True)
class Actor:
    id: int | None
    role: Role | None

    @classmethod
    def of(cls, user: User) -> "Actor":
        return cls(id=user.id, role=user.role)

    @property
    def is_principal(self) -> bool:
        return self.role == Role.PRINCIPAL


SYSTEM = Actor(id=None, role=None)


class EngineTx:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._emails: list[dict[str, Any]] = []
        self._audit: list[dict[str, Any]] = []

    def email(self, to: str | None, template: str, **params: Any) -> None:
        if to:
            self._emails.append(outbox_row(to, template, params))

    def audit(self, actor: Actor, action: str, entity_type: str, entity_id: int | None, **details: Any) -> None:
        self._audit.append(
            {
                "actor_id": actor.id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "details": details,
                "created_at": clock.utcnow(),
            }
        )

    async def _flush(self) -> None:
        if self._emails:
            await self.session.execute(insert(outbox_t), self._emails)
        if self._audit:
            await self.session.execute(insert(audit_t), self._audit)


@asynccontextmanager
async def engine_tx() -> AsyncIterator[EngineTx]:
    """Opens a fresh session + transaction holding the engine lock. Commits on success,
    rolls back on any exception (including DomainError)."""
    async with get_db().sessionmaker() as session, session.begin():
        # Must be the first statement: under READ COMMITTED every later statement then
        # sees everything committed by whoever held the lock before us.
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ENGINE_LOCK_KEY})
        tx = EngineTx(session)
        yield tx
        await tx._flush()
    if tx._emails:
        wake_outbox()
