"""Sign-up (email → code → password), login, password reset and password change."""

import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import burn_password_check, hash_password, verify_password
from app.models import User, users_t
from app.models.enums import CodePurpose
from app.services.auth import codes, sessions
from app.services.notify.outbox import enqueue_email, wake_outbox

log = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _user_by_email(session: AsyncSession, email: str, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(User.email == email)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


def _invalid_credentials() -> DomainError:
    return DomainError("INVALID_CREDENTIALS", "Incorrect email or password.", status_code=401)


# ---------------------------------------------------------------- sign-up


async def request_signup_code(session: AsyncSession, email: str) -> None:
    """Always "succeeds" from the caller's view so the response doesn't reveal who has an account."""
    email = normalize_email(email)
    await codes.check_rate_limit(session, email, CodePurpose.SIGNUP)
    user = await _user_by_email(session, email)
    ttl = get_settings().code_ttl_minutes
    if user is not None and user.is_activated:
        await codes.issue_code(session, email, CodePurpose.SIGNUP, usable=False)
        if user.is_active:
            await enqueue_email(session, email, "account_exists", {})
    elif user is not None and not user.is_active:
        await codes.issue_code(session, email, CodePurpose.SIGNUP, usable=False)
    else:
        code = await codes.issue_code(session, email, CodePurpose.SIGNUP)
        await enqueue_email(session, email, "signup_code", {"code": code, "ttl_minutes": ttl})
    await session.commit()
    wake_outbox()


async def verify_signup_code(session: AsyncSession, email: str, code: str) -> str:
    return await codes.verify_code(session, normalize_email(email), CodePurpose.SIGNUP, code)


async def complete_signup(
    session: AsyncSession,
    *,
    completion_token: str,
    first_name: str,
    last_name: str,
    password: str,
    phone: str | None,
    user_agent: str | None,
) -> tuple[User, str]:
    password_hash = await hash_password(password)
    email = await codes.consume_completion_token(session, completion_token, CodePurpose.SIGNUP)
    now = clock.utcnow()
    user = await _user_by_email(session, email, for_update=True)
    if user is not None:
        if user.is_activated:
            raise DomainError("ACCOUNT_EXISTS", "An account with this email already exists. Log in instead.")
        if not user.is_active:
            raise DomainError("ACCOUNT_DISABLED", "This account has been disabled.", status_code=403)
        # Staff created this account ahead of time: activate it, keeping the role they chose.
        user.password_hash = password_hash
        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone or user.phone
        user.email_verified_at = now
    else:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            password_hash=password_hash,
            email_verified_at=now,
        )
        session.add(user)
    await session.flush()
    token = await sessions.create_session(session, user.id, user_agent)
    await session.commit()
    return user, token


# ---------------------------------------------------------------- login


def _backoff_remaining(user: User) -> int:
    s = get_settings()
    excess = user.failed_login_count - s.login_failures_before_backoff
    if excess < 0 or user.last_failed_login_at is None:
        return 0
    delay = min(s.login_backoff_base_seconds * 2**excess, s.login_backoff_max_seconds)
    remaining = (user.last_failed_login_at + timedelta(seconds=delay)) - clock.utcnow()
    return max(0, int(remaining.total_seconds()))


async def login(session: AsyncSession, email: str, password: str, user_agent: str | None) -> tuple[User, str]:
    email = normalize_email(email)
    user = await _user_by_email(session, email)
    if user is None or user.password_hash is None:
        await burn_password_check(password)
        raise _invalid_credentials()
    wait = _backoff_remaining(user)
    if wait:
        raise DomainError(
            "TOO_MANY_ATTEMPTS",
            f"Too many failed attempts. Try again in {wait} seconds, or reset your password.",
            status_code=429,
            details={"retry_after": wait},
        )
    ok, new_hash = await verify_password(password, user.password_hash)
    if not ok:
        await session.execute(
            update(users_t)
            .where(users_t.c.id == user.id)
            .values(failed_login_count=users_t.c.failed_login_count + 1, last_failed_login_at=clock.utcnow())
        )
        await session.commit()
        raise _invalid_credentials()
    if not user.is_active:
        raise DomainError(
            "ACCOUNT_DISABLED", "This account has been disabled. Contact the school office.", status_code=403
        )
    user.failed_login_count = 0
    user.last_failed_login_at = None
    if new_hash:
        user.password_hash = new_hash
    token = await sessions.create_session(session, user.id, user_agent)
    await session.commit()
    return user, token


# ---------------------------------------------------------------- password reset / change


async def request_reset_code(session: AsyncSession, email: str) -> None:
    email = normalize_email(email)
    await codes.check_rate_limit(session, email, CodePurpose.PASSWORD_RESET)
    user = await _user_by_email(session, email)
    if user is not None and user.is_activated and user.is_active:
        code = await codes.issue_code(session, email, CodePurpose.PASSWORD_RESET)
        await enqueue_email(
            session, email, "reset_code", {"code": code, "ttl_minutes": get_settings().code_ttl_minutes}
        )
    else:
        await codes.issue_code(session, email, CodePurpose.PASSWORD_RESET, usable=False)
    await session.commit()
    wake_outbox()


async def verify_reset_code(session: AsyncSession, email: str, code: str) -> str:
    return await codes.verify_code(session, normalize_email(email), CodePurpose.PASSWORD_RESET, code)


async def complete_reset(
    session: AsyncSession, *, completion_token: str, new_password: str, user_agent: str | None
) -> tuple[User, str]:
    password_hash = await hash_password(new_password)
    email = await codes.consume_completion_token(session, completion_token, CodePurpose.PASSWORD_RESET)
    user = await _user_by_email(session, email, for_update=True)
    if user is None or not user.is_active:
        raise DomainError(
            "INVALID_TOKEN", "This verification has expired or was already used. Start again.", status_code=400
        )
    user.password_hash = password_hash
    user.failed_login_count = 0
    user.last_failed_login_at = None
    await sessions.revoke_all(session, user.id)
    token = await sessions.create_session(session, user.id, user_agent)
    await session.commit()
    return user, token


async def change_password(
    session: AsyncSession, user: User, *, current_password: str, new_password: str, current_session_id: int
) -> None:
    ok = user.password_hash is not None and (await verify_password(current_password, user.password_hash))[0]
    if not ok:
        raise DomainError("INVALID_CREDENTIALS", "Your current password is incorrect.", status_code=400)
    user.password_hash = await hash_password(new_password)
    await sessions.revoke_all(session, user.id, except_session_id=current_session_id)
    await session.commit()
