"""Class setup (Management/Principal) and teacher claims."""

from typing import Any

from sqlalchemy import RowMapping, delete, func, insert, select, update

from app.core import clock
from app.core.errors import DomainError, not_found
from app.models import classes_t, enrollments_t, students_t, users_t, waitlist_t
from app.models.enums import ACTIVE_STATUSES, CAN_TEACH_ROLES, Period
from app.services.engine import queries as q
from app.services.engine.promotion import promote
from app.services.engine.tx import Actor, EngineTx

EDITABLE_FIELDS = ("name", "description", "period", "capacity", "teacher_id", "published")


async def _require_teachable(tx: EngineTx, user_id: int) -> RowMapping:
    user = (await tx.session.execute(select(users_t).where(users_t.c.id == user_id))).mappings().first()
    if user is None or not user["is_active"] or user["role"] not in CAN_TEACH_ROLES:
        raise DomainError("INVALID_TEACHER", "That person can't be assigned as a teacher.", status_code=422)
    return user


async def _teacher_class_in_period(
    tx: EngineTx, teacher_id: int, period: Period, *, exclude_class_id: int | None
) -> RowMapping | None:
    stmt = select(classes_t.c.id, classes_t.c.name).where(
        classes_t.c.teacher_id == teacher_id, classes_t.c.period == period
    )
    if exclude_class_id is not None:
        stmt = stmt.where(classes_t.c.id != exclude_class_id)
    return (await tx.session.execute(stmt)).mappings().first()


def _teacher_conflict(period: Period, other: RowMapping, *, self_claim: bool = False) -> DomainError:
    who = "You already teach" if self_claim else "That teacher already has"
    return DomainError(
        "TEACHER_PERIOD_CONFLICT",
        f"{who} a {period.label} class ({other['name']}).",
        details={"class_id": other["id"], "class_name": other["name"]},
    )


async def _next_sort_order(tx: EngineTx, period: Period) -> int:
    current = (
        await tx.session.execute(select(func.max(classes_t.c.sort_order)).where(classes_t.c.period == period))
    ).scalar_one()
    return 0 if current is None else current + 1


async def create_class(
    tx: EngineTx,
    actor: Actor,
    *,
    name: str,
    description: str,
    period: Period,
    capacity: int,
    teacher_id: int | None,
    published: bool,
) -> int:
    if teacher_id is not None:
        await _require_teachable(tx, teacher_id)
        other = await _teacher_class_in_period(tx, teacher_id, period, exclude_class_id=None)
        if other is not None:
            raise _teacher_conflict(period, other)
    now = clock.utcnow()
    class_id = (
        await tx.session.execute(
            insert(classes_t)
            .values(
                name=name,
                description=description,
                period=period,
                capacity=capacity,
                teacher_id=teacher_id,
                # Staff-assigned teachers are "locked": they can't drop the class themselves.
                teacher_locked=teacher_id is not None,
                published=published,
                sort_order=await _next_sort_order(tx, period),
                created_at=now,
                updated_at=now,
            )
            .returning(classes_t.c.id)
        )
    ).scalar_one()
    tx.audit(actor, "class.created", "class", class_id, name=name, period=period.value)
    return class_id


async def update_class(tx: EngineTx, actor: Actor, class_id: int, changes: dict[str, Any]) -> None:
    """Applies only the provided fields. Conflicts are rejected up front rather than silently
    double-booking anyone."""
    changes = {k: v for k, v in changes.items() if k in EDITABLE_FIELDS}
    cls = await q.require_class(tx, class_id)
    old_period = Period(cls["period"])
    new_period = Period(changes.get("period", old_period))
    new_teacher = changes["teacher_id"] if "teacher_id" in changes else cls["teacher_id"]
    teacher_changed = "teacher_id" in changes and new_teacher != cls["teacher_id"]
    values: dict[str, Any] = {}

    if teacher_changed and new_teacher is not None:
        await _require_teachable(tx, new_teacher)
    if new_teacher is not None and (teacher_changed or new_period != old_period):
        other = await _teacher_class_in_period(tx, new_teacher, new_period, exclude_class_id=cls["id"])
        if other is not None:
            raise _teacher_conflict(new_period, other)

    if new_period != old_period:
        mine, theirs = enrollments_t.alias("mine"), enrollments_t.alias("theirs")
        other_cls = classes_t.alias("other_cls")
        conflicts = (
            await tx.session.execute(
                select(students_t.c.id, students_t.c.first_name, students_t.c.last_name, other_cls.c.name)
                .select_from(mine)
                .join(students_t, students_t.c.id == mine.c.student_id)
                .join(
                    theirs,
                    (theirs.c.student_id == mine.c.student_id)
                    & (theirs.c.period == new_period)
                    & theirs.c.status.in_(ACTIVE_STATUSES)
                    & (theirs.c.class_id != cls["id"]),
                )
                .join(other_cls, other_cls.c.id == theirs.c.class_id)
                .where(mine.c.class_id == cls["id"], mine.c.status.in_(ACTIVE_STATUSES))
                .order_by(students_t.c.last_name, students_t.c.first_name)
            )
        ).all()
        if conflicts:
            names = ", ".join(f"{r.first_name} {r.last_name}" for r in conflicts)
            raise DomainError(
                "STUDENT_PERIOD_CONFLICT",
                f"Can't move this class to {new_period.label}: {names} already have a class then.",
                details=[
                    {"student_id": r.id, "student_name": f"{r.first_name} {r.last_name}", "class_name": r.name}
                    for r in conflicts
                ],
            )
        values["period"] = new_period
        values["sort_order"] = await _next_sort_order(tx, new_period)

    if "capacity" in changes:
        taken = await q.seats_taken(tx, cls["id"])
        if changes["capacity"] < taken:
            raise DomainError(
                "CAPACITY_BELOW_ENROLLED",
                f"{taken} students already hold seats in this class; "
                f"remove some before lowering capacity to {changes['capacity']}.",
                details={"seats_taken": taken},
            )
        values["capacity"] = changes["capacity"]

    if "teacher_id" in changes:
        values["teacher_id"] = new_teacher
        if new_teacher is None:
            values["teacher_locked"] = False
        elif teacher_changed:
            values["teacher_locked"] = True

    for field in ("name", "description", "published"):
        if field in changes:
            values[field] = changes[field]

    if values:
        values["updated_at"] = clock.utcnow()
        # A period change cascades to enrollments.period through the composite FK.
        await tx.session.execute(update(classes_t).where(classes_t.c.id == cls["id"]).values(**values))
    if values.get("capacity", cls["capacity"]) > cls["capacity"]:
        await promote(tx, [cls["id"]])
    tx.audit(actor, "class.updated", "class", cls["id"], changes=changes)


async def delete_class(tx: EngineTx, actor: Actor, class_id: int) -> None:
    cls = await q.require_class(tx, class_id)
    period = Period(cls["period"])
    affected = (
        await tx.session.execute(
            select(students_t.c.first_name, students_t.c.last_name, users_t.c.email)
            .select_from(enrollments_t)
            .join(students_t, students_t.c.id == enrollments_t.c.student_id)
            .join(users_t, users_t.c.id == students_t.c.family_id)
            .where(enrollments_t.c.class_id == cls["id"], enrollments_t.c.status.in_(ACTIVE_STATUSES))
        )
    ).all()
    waitlisted = (
        await tx.session.execute(
            select(students_t.c.first_name, students_t.c.last_name, users_t.c.email)
            .select_from(waitlist_t)
            .join(students_t, students_t.c.id == waitlist_t.c.student_id)
            .join(users_t, users_t.c.id == students_t.c.family_id)
            .where(waitlist_t.c.class_id == cls["id"])
        )
    ).all()
    await tx.session.execute(delete(classes_t).where(classes_t.c.id == cls["id"]))
    for rows, is_waitlist in ((affected, False), (waitlisted, True)):
        for r in rows:
            tx.email(
                r.email,
                "class_cancelled",
                student_name=f"{r.first_name} {r.last_name}",
                class_name=cls["name"],
                period_label=period.label,
                waitlisted=is_waitlist,
            )
    tx.audit(
        actor, "class.deleted", "class", cls["id"], name=cls["name"], enrolled=len(affected), waitlisted=len(waitlisted)
    )


async def move_class(tx: EngineTx, actor: Actor, class_id: int, direction: str) -> None:
    """Swaps a class with its neighbour among classes of the same period and publish state."""
    cls = await q.require_class(tx, class_id)
    group = (
        (
            await tx.session.execute(
                select(classes_t.c.id)
                .where(classes_t.c.period == cls["period"], classes_t.c.published == cls["published"])
                .order_by(classes_t.c.sort_order, classes_t.c.id)
            )
        )
        .scalars()
        .all()
    )
    idx = group.index(cls["id"])
    swap = idx - 1 if direction == "up" else idx + 1
    if swap < 0 or swap >= len(group):
        return
    group[idx], group[swap] = group[swap], group[idx]
    for position, cid in enumerate(group):
        await tx.session.execute(update(classes_t).where(classes_t.c.id == cid).values(sort_order=position))
    tx.audit(actor, "class.moved", "class", cls["id"], direction=direction)


async def claim(tx: EngineTx, actor: Actor, class_id: int) -> None:
    """A teacher claims one unclaimed, published class per period."""
    cls = await q.require_class(tx, class_id)
    if not cls["published"]:
        raise not_found("Class")
    if cls["teacher_id"] == actor.id:
        raise DomainError("ALREADY_CLAIMED", "You already teach this class.")
    if cls["teacher_id"] is not None:
        raise DomainError("ALREADY_CLAIMED", "Another teacher already claimed this class.")
    period = Period(cls["period"])
    other = await _teacher_class_in_period(tx, actor.id, period, exclude_class_id=None)
    if other is not None:
        raise _teacher_conflict(period, other, self_claim=True)
    await tx.session.execute(
        update(classes_t)
        .where(classes_t.c.id == cls["id"])
        .values(teacher_id=actor.id, teacher_locked=False, updated_at=clock.utcnow())
    )
    tx.audit(actor, "class.claimed", "class", cls["id"])


async def drop_claim(tx: EngineTx, actor: Actor, class_id: int) -> None:
    cls = await q.require_class(tx, class_id)
    if cls["teacher_id"] != actor.id:
        raise not_found("Class")
    if cls["teacher_locked"]:
        raise DomainError(
            "CLAIM_LOCKED",
            "The school assigned you to this class, so only Management can change it.",
            status_code=403,
        )
    await tx.session.execute(
        update(classes_t)
        .where(classes_t.c.id == cls["id"])
        .values(teacher_id=None, teacher_locked=False, updated_at=clock.utcnow())
    )
    tx.audit(actor, "class.unclaimed", "class", cls["id"])
