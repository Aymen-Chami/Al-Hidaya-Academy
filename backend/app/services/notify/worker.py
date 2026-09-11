"""Delivers queued emails.

Rows are leased (claimed with FOR UPDATE SKIP LOCKED and pushed into the future) in a short
transaction, sent outside any transaction, then marked sent — or rescheduled with backoff.
Safe to run in several processes at once.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.core import clock
from app.core.config import get_settings
from app.db.session import get_db
from app.models import email_codes_t, outbox_t, sessions_t
from app.services.notify.backends import EmailBackend, get_backend
from app.services.notify.outbox import register_wake_callback, unregister_wake_callback
from app.services.notify.templates import SECRET_PARAMS, render

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=5)
HOUSEKEEPING_EVERY = timedelta(hours=1)


def _backoff(attempts: int) -> timedelta:
    return min(timedelta(seconds=30 * 2**attempts), timedelta(hours=1))


class OutboxWorker:
    def __init__(self, backend: EmailBackend | None = None) -> None:
        self.backend = backend or get_backend()
        self._wake = asyncio.Event()
        self._last_housekeeping = None

    def wake(self) -> None:
        self._wake.set()

    async def run_once(self, batch_size: int = 20) -> int:
        """Send due emails. Returns how many were attempted."""
        s = get_settings()
        db = get_db()
        now = clock.utcnow()
        async with db.sessionmaker() as session, session.begin():
            rows = (
                await session.execute(
                    select(
                        outbox_t.c.id, outbox_t.c.to_email, outbox_t.c.template, outbox_t.c.params, outbox_t.c.attempts
                    )
                    .where(
                        outbox_t.c.sent_at.is_(None),
                        outbox_t.c.next_attempt_at <= now,
                        outbox_t.c.attempts < s.outbox_max_attempts,
                    )
                    .order_by(outbox_t.c.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if rows:
                await session.execute(
                    update(outbox_t).where(outbox_t.c.id.in_([r.id for r in rows])).values(next_attempt_at=now + LEASE)
                )

        for row in rows:
            try:
                subject, body = render(row.template, row.params)
                await self.backend.send(row.to_email, subject, body)
            except Exception as exc:
                attempts = row.attempts + 1
                if attempts >= s.outbox_max_attempts:
                    log.error("Giving up on outbox email %s (%s): %s", row.id, row.template, exc)
                else:
                    log.warning("Outbox email %s (%s) failed, will retry: %s", row.id, row.template, exc)
                values = {
                    "attempts": attempts,
                    "last_error": str(exc)[:1000],
                    "next_attempt_at": clock.utcnow() + _backoff(attempts),
                }
            else:
                values = {
                    "sent_at": clock.utcnow(),
                    "attempts": row.attempts + 1,
                    "last_error": None,
                    "params": {k: v for k, v in row.params.items() if k not in SECRET_PARAMS},
                }
            async with db.sessionmaker() as session, session.begin():
                await session.execute(update(outbox_t).where(outbox_t.c.id == row.id).values(**values))
        return len(rows)

    async def housekeeping(self) -> None:
        now = clock.utcnow()
        async with get_db().sessionmaker() as session, session.begin():
            await session.execute(delete(sessions_t).where(sessions_t.c.expires_at < now))
            await session.execute(delete(email_codes_t).where(email_codes_t.c.created_at < now - timedelta(days=1)))
            await session.execute(
                delete(outbox_t).where(outbox_t.c.sent_at.is_not(None), outbox_t.c.sent_at < now - timedelta(days=30))
            )

    async def run_forever(self) -> None:
        register_wake_callback(self.wake)
        try:
            while True:
                try:
                    sent = await self.run_once()
                    now = clock.utcnow()
                    if self._last_housekeeping is None or now - self._last_housekeeping > HOUSEKEEPING_EVERY:
                        await self.housekeeping()
                        self._last_housekeeping = now
                except Exception:
                    log.exception("Outbox worker iteration failed")
                    sent = 0
                if sent:
                    continue  # there may be more waiting
                self._wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=get_settings().outbox_poll_seconds)
        finally:
            unregister_wake_callback(self.wake)
