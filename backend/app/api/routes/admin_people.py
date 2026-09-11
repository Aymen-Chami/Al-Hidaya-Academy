"""Students and accounts. Management can view people and manage children; only the Principal
creates staff accounts, changes roles, deactivates accounts, or deletes children."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, PrincipalUser, SessionDep, actor
from app.core.errors import not_found
from app.models.enums import Role
from app.schemas.admin import (
    AdminStudentIn,
    AdminStudentOut,
    AdminStudentUpdateIn,
    AuditEventOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from app.services.engine import people
from app.services.engine.tx import engine_tx
from app.services.queries import admin

router = APIRouter(prefix="/admin", tags=["admin: people"])


async def _student_out(session, student_id: int) -> AdminStudentOut:
    rows = await admin.list_students(session, student_id=student_id)
    if not rows:
        raise not_found("Student")
    return AdminStudentOut.model_validate(rows[0])


async def _user_out(session, user_id: int) -> UserOut:
    rows = await admin.list_users(session, user_id=user_id)
    if not rows:
        raise not_found("User")
    return UserOut.model_validate(rows[0])


@router.get("/students")
async def list_students(
    user: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search child name or family email")] = None,
    family_id: int | None = None,
) -> list[AdminStudentOut]:
    return [AdminStudentOut.model_validate(s) for s in await admin.list_students(session, q=q, family_id=family_id)]


@router.post("/students", status_code=status.HTTP_201_CREATED)
async def create_student(body: AdminStudentIn, user: AdminUser, session: SessionDep) -> AdminStudentOut:
    """Create a child, optionally linked to a family account (walk-ins can have none)."""
    async with engine_tx() as tx:
        student_id = await people.create_student(
            tx, actor(user), family_id=body.family_id, first_name=body.first_name, last_name=body.last_name
        )
    return await _student_out(session, student_id)


@router.patch("/students/{student_id}")
async def update_student(
    student_id: int, body: AdminStudentUpdateIn, user: AdminUser, session: SessionDep
) -> AdminStudentOut:
    changes = body.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    async with engine_tx() as tx:
        await people.update_student(tx, actor(user), student_id, changes, as_staff=True)
    return await _student_out(session, student_id)


@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int, user: PrincipalUser) -> None:
    async with engine_tx() as tx:
        await people.delete_student(tx, actor(user), student_id, as_staff=True)


@router.get("/users")
async def list_users(
    user: AdminUser,
    session: SessionDep,
    role: Role | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Search name or email")] = None,
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await admin.list_users(session, role=role, q=q)]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreateIn, user: PrincipalUser, session: SessionDep) -> UserOut:
    """Prepare an account (e.g. a teacher). They activate it by signing up with this email and
    keep the role set here. An invitation email is sent unless send_invite is false."""
    async with engine_tx() as tx:
        user_id = await people.create_user(tx, actor(user), **body.model_dump())
    return await _user_out(session, user_id)


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserUpdateIn, user: PrincipalUser, session: SessionDep) -> UserOut:
    """Change names, role or active status. Losing teaching rights (or being deactivated) unassigns
    their classes; deactivation also signs them out everywhere. The last Principal can't be removed."""
    changes = body.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name", "role", "is_active"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    for field in ("display_name", "phone"):
        if field in changes and not changes[field]:
            changes[field] = None
    async with engine_tx() as tx:
        await people.update_user(tx, actor(user), user_id, changes)
    return await _user_out(session, user_id)


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_sessions(user_id: int, user: PrincipalUser) -> None:
    async with engine_tx() as tx:
        await people.revoke_sessions(tx, actor(user), user_id)


@router.get("/audit")
async def audit_log(
    user: PrincipalUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_id: int | None = None,
) -> list[AuditEventOut]:
    """Who did what, newest first. Page with before_id = the last id you received."""
    return [AuditEventOut.model_validate(e) for e in await admin.list_audit(session, limit=limit, before_id=before_id)]
