from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import DomainError, forbidden
from app.db.session import get_db
from app.models import User
from app.models.enums import ADMIN_ROLES, CAN_TEACH_ROLES, PRINCIPAL_ROLES, TEACHER_ROLES, Role
from app.services.auth.sessions import resolve_session
from app.services.engine.tx import Actor


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session for reads and auth flows. Engine mutations open their own."""
    async with get_db().sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_optional_user(request: Request, session: SessionDep) -> User | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    resolved = await resolve_session(session, token)
    # End the read transaction so this request doesn't sit on a pooled connection while an engine
    # transaction (which uses its own connection) waits for the lock. Commit, not rollback:
    # rollback would expire `user` (expire_on_commit is off, so commit keeps it loaded).
    await session.commit()
    if resolved is None:
        return None
    user, session_id = resolved
    request.state.session_id = session_id
    return user


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise DomainError("UNAUTHENTICATED", "Please log in.", status_code=401)
    return user


def require_roles(roles: frozenset[Role]):
    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(ADMIN_ROLES))]
PrincipalUser = Annotated[User, Depends(require_roles(PRINCIPAL_ROLES))]
TeacherUser = Annotated[User, Depends(require_roles(TEACHER_ROLES))]
CanTeachUser = Annotated[User, Depends(require_roles(CAN_TEACH_ROLES))]


def actor(user: User) -> Actor:
    return Actor.of(user)
