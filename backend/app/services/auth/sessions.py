from datetime import timedelta

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models import User, UserSession, sessions_t


async def create_session(session: AsyncSession, user_id: int, user_agent: str | None) -> str:
    """Creates a session row (caller commits) and returns the raw token for the cookie."""
    token = new_token()
    now = clock.utcnow()
    await session.execute(
        insert(sessions_t).values(
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=get_settings().session_ttl_days),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    return token


async def resolve_session(session: AsyncSession, token: str) -> tuple[User, int] | None:
    """Returns (user, session_id) for a valid, unexpired session of an active user."""
    now = clock.utcnow()
    row = (
        await session.execute(
            select(User, UserSession.id, UserSession.last_used_at)
            .join(UserSession, UserSession.user_id == User.id)
            .where(UserSession.token_hash == hash_token(token), UserSession.expires_at > now, User.is_active.is_(True))
        )
    ).first()
    if row is None:
        return None
    user, session_id, last_used_at = row
    # Polling clients hit the API every few seconds; only record activity occasionally.
    if now - last_used_at > timedelta(seconds=get_settings().session_touch_interval_seconds):
        await session.execute(update(sessions_t).where(sessions_t.c.id == session_id).values(last_used_at=now))
        await session.commit()
    return user, session_id


async def revoke_token(session: AsyncSession, token: str) -> None:
    await session.execute(delete(sessions_t).where(sessions_t.c.token_hash == hash_token(token)))


async def revoke_all(session: AsyncSession, user_id: int, *, except_session_id: int | None = None) -> None:
    stmt = delete(sessions_t).where(sessions_t.c.user_id == user_id)
    if except_session_id is not None:
        stmt = stmt.where(sessions_t.c.id != except_session_id)
    await session.execute(stmt)
