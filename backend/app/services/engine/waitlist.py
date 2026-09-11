from sqlalchemy import delete, insert, select, update

from app.core import clock
from app.core.errors import DomainError, not_found
from app.models import waitlist_t
from app.services.engine import queries as q
from app.services.engine.tx import Actor, EngineTx


async def join(tx: EngineTx, actor: Actor, *, student_id: int, class_id: int) -> int:
    """Waitlists are not period-restricted: a child can hold one class in a period and wait for
    others in it. Joining is only allowed once the class is full."""
    student = await q.require_student(tx, student_id, actor=actor)
    cls = await q.require_class(tx, class_id)
    if not cls["published"]:
        raise not_found("Class")
    if cls["teacher_id"] is None:
        raise DomainError("CLASS_NOT_OPEN", "This class doesn't have a teacher yet, so sign-ups aren't open.")
    if await q.active_in_class(tx, student.id, cls["id"]):
        raise q.already_enrolled(student)
    exists = (
        await tx.session.execute(
            select(waitlist_t.c.id).where(waitlist_t.c.student_id == student.id, waitlist_t.c.class_id == cls["id"])
        )
    ).first()
    if exists:
        raise DomainError("ALREADY_WAITLISTED", f"{student.name} is already on this waitlist.")
    if await q.seats_taken(tx, cls["id"]) < cls["capacity"]:
        raise DomainError("HAS_OPEN_SEATS", "This class still has open seats — sign up instead.")
    entry_id = (
        await tx.session.execute(
            insert(waitlist_t)
            .values(
                student_id=student.id, class_id=cls["id"], priority=None, created_by=actor.id, created_at=clock.utcnow()
            )
            .returning(waitlist_t.c.id)
        )
    ).scalar_one()
    tx.audit(actor, "waitlist.joined", "waitlist_entry", entry_id, student_id=student.id, class_id=cls["id"])
    return entry_id


async def _load_entry(tx: EngineTx, entry_id: int):
    row = (await tx.session.execute(select(waitlist_t).where(waitlist_t.c.id == entry_id))).mappings().first()
    if row is None:
        raise not_found("Waitlist entry")
    return row


async def set_priority(tx: EngineTx, actor: Actor, entry_id: int, priority: int | None) -> None:
    """Sets 1st/2nd/3rd choice (or unranked). A rank is unique per child, so claiming it here
    clears it from their other entries. No seat changes: every waitlisted class is full."""
    entry = await _load_entry(tx, entry_id)
    await q.require_student(tx, entry["student_id"], actor=actor)
    if priority is not None:
        # Clear first, then set: two statements in this order keep the unique index happy.
        await tx.session.execute(
            update(waitlist_t)
            .where(
                waitlist_t.c.student_id == entry["student_id"],
                waitlist_t.c.priority == priority,
                waitlist_t.c.id != entry_id,
            )
            .values(priority=None)
        )
    await tx.session.execute(update(waitlist_t).where(waitlist_t.c.id == entry_id).values(priority=priority))
    tx.audit(actor, "waitlist.priority_set", "waitlist_entry", entry_id, priority=priority)


async def leave(tx: EngineTx, actor: Actor, entry_id: int, *, as_staff: bool) -> None:
    entry = await _load_entry(tx, entry_id)
    await q.require_student(tx, entry["student_id"], actor=None if as_staff else actor)
    await tx.session.execute(delete(waitlist_t).where(waitlist_t.c.id == entry_id))
    tx.audit(
        actor,
        "waitlist.removed" if as_staff else "waitlist.left",
        "waitlist_entry",
        entry_id,
        student_id=entry["student_id"],
        class_id=entry["class_id"],
    )
