from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import outbox_t

_wake_callbacks: list = []


def outbox_row(to: str, template: str, params: dict[str, Any]) -> dict[str, Any]:
    # Timestamps come from the app clock (not the DB's now()) because the worker compares against it.
    now = clock.utcnow()
    return {"to_email": to, "template": template, "params": params, "created_at": now, "next_attempt_at": now}


async def enqueue_email(session: AsyncSession, to: str, template: str, params: dict[str, Any]) -> None:
    """Queue an email inside the caller's transaction; it's delivered only if that transaction commits."""
    await session.execute(insert(outbox_t).values(**outbox_row(to, template, params)))


def register_wake_callback(callback) -> None:
    _wake_callbacks.append(callback)


def unregister_wake_callback(callback) -> None:
    if callback in _wake_callbacks:
        _wake_callbacks.remove(callback)


def wake_outbox() -> None:
    """Call after committing a transaction that queued email so it goes out right away."""
    for callback in list(_wake_callbacks):
        callback()
