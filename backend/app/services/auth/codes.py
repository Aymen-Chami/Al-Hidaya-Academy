"""One-time email codes and the single-use completion tokens they unlock."""

from datetime import timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.errors import DomainError, bad_request
from app.core.security import code_mac, generate_code, hash_token, macs_equal, new_token
from app.models import email_codes_t
from app.models.enums import CodePurpose


def _invalid_code() -> DomainError:
    return bad_request("INVALID_CODE", "That code is incorrect or has expired. Request a new one.")


async def check_rate_limit(session: AsyncSession, email: str, purpose: CodePurpose) -> None:
    s = get_settings()
    now = clock.utcnow()
    last, count = (
        await session.execute(
            select(func.max(email_codes_t.c.created_at), func.count()).where(
                email_codes_t.c.email == email,
                email_codes_t.c.purpose == purpose,
                email_codes_t.c.created_at > now - timedelta(hours=1),
            )
        )
    ).one()
    if last is not None and now - last < timedelta(seconds=s.code_resend_cooldown_seconds):
        wait = s.code_resend_cooldown_seconds - int((now - last).total_seconds())
        raise DomainError(
            "RATE_LIMITED",
            f"Please wait {wait}s before requesting another code.",
            status_code=429,
            details={"retry_after": wait},
        )
    if count >= s.code_max_per_hour:
        raise DomainError("RATE_LIMITED", "Too many codes requested. Try again later.", status_code=429)


async def issue_code(session: AsyncSession, email: str, purpose: CodePurpose, *, usable: bool = True) -> str:
    """Creates a code row (invalidating earlier ones). `usable=False` records the request for
    rate limiting without creating anything that can be verified (e.g. account already exists)."""
    now = clock.utcnow()
    await session.execute(
        update(email_codes_t)
        .where(
            email_codes_t.c.email == email, email_codes_t.c.purpose == purpose, email_codes_t.c.consumed_at.is_(None)
        )
        .values(consumed_at=now)
    )
    code = generate_code()
    await session.execute(
        insert(email_codes_t).values(
            email=email,
            purpose=purpose,
            code_mac=code_mac(purpose, email, code),
            expires_at=now + timedelta(minutes=get_settings().code_ttl_minutes),
            created_at=now,
            consumed_at=None if usable else now,
        )
    )
    return code


async def verify_code(session: AsyncSession, email: str, purpose: CodePurpose, code: str) -> str:
    """Checks the latest code; on success returns a single-use completion token. Commits."""
    s = get_settings()
    now = clock.utcnow()
    row = (
        await session.execute(
            select(email_codes_t.c.id, email_codes_t.c.code_mac)
            .where(
                email_codes_t.c.email == email,
                email_codes_t.c.purpose == purpose,
                email_codes_t.c.consumed_at.is_(None),
                email_codes_t.c.expires_at > now,
            )
            .order_by(email_codes_t.c.created_at.desc(), email_codes_t.c.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise _invalid_code()
    # Count the attempt atomically so parallel guesses can't exceed the limit.
    counted = (
        await session.execute(
            update(email_codes_t)
            .where(email_codes_t.c.id == row.id, email_codes_t.c.attempts < s.code_max_attempts)
            .values(attempts=email_codes_t.c.attempts + 1)
            .returning(email_codes_t.c.id)
        )
    ).first()
    if counted is None or not macs_equal(row.code_mac, code_mac(purpose, email, code.strip())):
        await session.commit()
        raise _invalid_code()
    token = new_token()
    await session.execute(
        update(email_codes_t)
        .where(email_codes_t.c.id == row.id)
        .values(
            verified_at=now,
            completion_token_hash=hash_token(token),
            completion_expires_at=now + timedelta(minutes=s.completion_token_ttl_minutes),
        )
    )
    await session.commit()
    return token


async def consume_completion_token(session: AsyncSession, token: str, purpose: CodePurpose) -> str:
    """Marks the token used and returns its email. Only one caller can ever succeed. Caller commits."""
    row = (
        await session.execute(
            update(email_codes_t)
            .where(
                email_codes_t.c.completion_token_hash == hash_token(token),
                email_codes_t.c.purpose == purpose,
                email_codes_t.c.consumed_at.is_(None),
                email_codes_t.c.completion_expires_at > clock.utcnow(),
            )
            .values(consumed_at=clock.utcnow())
            .returning(email_codes_t.c.email)
        )
    ).first()
    if row is None:
        raise bad_request("INVALID_TOKEN", "This verification has expired or was already used. Start again.")
    return row.email
