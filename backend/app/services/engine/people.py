"""Children (students) and accounts (users). Changes that free seats go through promotion."""

from typing import Any

from sqlalchemy import delete, func, insert, select, update

from app.core import clock
from app.core.errors import DomainError, not_found
from app.models import classes_t, enrollments_t, sessions_t, students_t, users_t, waitlist_t
from app.models.enums import ACTIVE_STATUSES, CAN_TEACH_ROLES, Role
from app.services.engine import queries as q
from app.services.engine.promotion import promote
from app.services.engine.tx import Actor, EngineTx

# ---------------------------------------------------------------- students


async def create_student(tx: EngineTx, actor: Actor, *, family_id: int | None, first_name: str, last_name: str) -> int:
    if family_id is not None:
        family = (await tx.session.execute(select(users_t.c.id).where(users_t.c.id == family_id))).first()
        if family is None:
            raise DomainError("INVALID_FAMILY", "That family account doesn't exist.", status_code=422)
    student_id = (
        await tx.session.execute(
            insert(students_t)
            .values(
                family_id=family_id,
                first_name=first_name,
                last_name=last_name,
                created_by=actor.id,
                created_at=clock.utcnow(),
            )
            .returning(students_t.c.id)
        )
    ).scalar_one()
    tx.audit(actor, "student.created", "student", student_id, family_id=family_id)
    return student_id


async def update_student(
    tx: EngineTx, actor: Actor, student_id: int, changes: dict[str, Any], *, as_staff: bool
) -> None:
    await q.require_student(tx, student_id, actor=None if as_staff else actor)
    allowed = ("first_name", "last_name", "family_id") if as_staff else ("first_name", "last_name")
    values = {k: v for k, v in changes.items() if k in allowed}
    if values.get("family_id") is not None:
        family = (await tx.session.execute(select(users_t.c.id).where(users_t.c.id == values["family_id"]))).first()
        if family is None:
            raise DomainError("INVALID_FAMILY", "That family account doesn't exist.", status_code=422)
    if values:
        await tx.session.execute(update(students_t).where(students_t.c.id == student_id).values(**values))
        tx.audit(actor, "student.updated", "student", student_id, fields=sorted(values))


async def delete_student(tx: EngineTx, actor: Actor, student_id: int, *, as_staff: bool) -> None:
    """Removes a child with all their enrollments and waitlist entries; freed seats are refilled."""
    await q.require_student(tx, student_id, actor=None if as_staff else actor)
    freed = (
        (
            await tx.session.execute(
                select(enrollments_t.c.class_id).where(
                    enrollments_t.c.student_id == student_id, enrollments_t.c.status.in_(ACTIVE_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )
    await tx.session.execute(delete(enrollments_t).where(enrollments_t.c.student_id == student_id))
    await tx.session.execute(delete(waitlist_t).where(waitlist_t.c.student_id == student_id))
    await tx.session.execute(delete(students_t).where(students_t.c.id == student_id))
    await promote(tx, freed)
    tx.audit(actor, "student.deleted", "student", student_id, freed_class_ids=list(freed))


# ---------------------------------------------------------------- users (Principal only)


async def create_user(
    tx: EngineTx,
    actor: Actor,
    *,
    email: str,
    first_name: str,
    last_name: str,
    display_name: str | None,
    phone: str | None,
    role: Role,
    send_invite: bool,
) -> int:
    """Creates an account ahead of time (no password). The person activates it through the normal
    sign-up flow with this email and keeps the role chosen here."""
    exists = (await tx.session.execute(select(users_t.c.id).where(users_t.c.email == email))).first()
    if exists:
        raise DomainError("EMAIL_TAKEN", "An account with this email already exists.")
    now = clock.utcnow()
    user_id = (
        await tx.session.execute(
            insert(users_t)
            .values(
                email=email,
                first_name=first_name,
                last_name=last_name,
                display_name=display_name,
                phone=phone,
                role=role,
                created_at=now,
                updated_at=now,
            )
            .returning(users_t.c.id)
        )
    ).scalar_one()
    if send_invite:
        tx.email(email, "account_invite", first_name=first_name, role=role.value)
    tx.audit(actor, "user.created", "user", user_id, role=role.value)
    return user_id


async def _active_principals_other_than(tx: EngineTx, user_id: int) -> int:
    return (
        await tx.session.execute(
            select(func.count()).where(
                users_t.c.role == Role.PRINCIPAL, users_t.c.is_active.is_(True), users_t.c.id != user_id
            )
        )
    ).scalar_one()


async def update_user(tx: EngineTx, actor: Actor, user_id: int, changes: dict[str, Any]) -> None:
    user = (await tx.session.execute(select(users_t).where(users_t.c.id == user_id))).mappings().first()
    if user is None:
        raise not_found("User")
    values = {
        k: v
        for k, v in changes.items()
        if k in ("first_name", "last_name", "display_name", "phone", "role", "is_active")
    }
    new_role = values.get("role", user["role"])
    new_active = values.get("is_active", user["is_active"])

    stops_being_principal = (
        user["role"] == Role.PRINCIPAL and user["is_active"] and (new_role != Role.PRINCIPAL or not new_active)
    )
    if stops_being_principal and await _active_principals_other_than(tx, user_id) == 0:
        raise DomainError("LAST_PRINCIPAL", "There must always be at least one active Principal.")

    if not new_active or new_role not in CAN_TEACH_ROLES:
        # They can no longer teach: free up any classes they were teaching.
        await tx.session.execute(
            update(classes_t)
            .where(classes_t.c.teacher_id == user_id)
            .values(teacher_id=None, teacher_locked=False, updated_at=clock.utcnow())
        )
    if not new_active:
        await tx.session.execute(delete(sessions_t).where(sessions_t.c.user_id == user_id))

    if values:
        values["updated_at"] = clock.utcnow()
        await tx.session.execute(update(users_t).where(users_t.c.id == user_id).values(**values))
    tx.audit(actor, "user.updated", "user", user_id, changes={k: v for k, v in values.items() if k != "updated_at"})


async def revoke_sessions(tx: EngineTx, actor: Actor, user_id: int) -> None:
    exists = (await tx.session.execute(select(users_t.c.id).where(users_t.c.id == user_id))).first()
    if exists is None:
        raise not_found("User")
    await tx.session.execute(delete(sessions_t).where(sessions_t.c.user_id == user_id))
    tx.audit(actor, "user.sessions_revoked", "user", user_id)
