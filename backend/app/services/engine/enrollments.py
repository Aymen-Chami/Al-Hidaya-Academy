from dataclasses import dataclass, field

from sqlalchemy import delete, select, update

from app.core import clock
from app.core.errors import DomainError, not_found
from app.models import classes_t, enrollments_t
from app.models.enums import ACTIVE_STATUSES, EnrollmentSource, EnrollmentStatus, Period
from app.services.engine import queries as q
from app.services.engine.promotion import promote
from app.services.engine.tx import Actor, EngineTx


async def sign_up(tx: EngineTx, actor: Actor, *, student_id: int, class_id: int) -> int:
    """A family requests a seat for their child. Starts Pending and holds the seat."""
    student = await q.require_student(tx, student_id, actor=actor)
    cls = await q.require_class(tx, class_id)
    if not cls["published"]:
        raise not_found("Class")
    if cls["teacher_id"] is None:
        raise DomainError("CLASS_NOT_OPEN", "This class doesn't have a teacher yet, so sign-ups aren't open.")
    if await q.active_in_class(tx, student.id, cls["id"]):
        raise q.already_enrolled(student)
    other = await q.active_in_period(tx, student.id, Period(cls["period"]))
    if other is not None:
        raise q.period_conflict(student, other)
    if await q.seats_taken(tx, cls["id"]) >= cls["capacity"]:
        raise q.class_full()
    enrollment_id = await q.upsert_enrollment(
        tx,
        student_id=student.id,
        cls=cls,
        status=EnrollmentStatus.PENDING,
        source=EnrollmentSource.FAMILY,
        created_by=actor.id,
    )
    if enrollment_id is None:
        raise q.already_enrolled(student)
    await q.delete_waitlist_entry(tx, student.id, cls["id"])
    tx.audit(actor, "enrollment.requested", "enrollment", enrollment_id, student_id=student.id, class_id=cls["id"])
    return enrollment_id


async def staff_enroll(tx: EngineTx, actor: Actor, *, class_id: int, student_id: int) -> tuple[int, EnrollmentStatus]:
    """Management/Principal add a child directly (drafts and teacherless classes allowed).
    Approved when the Principal does it; Pending (awaiting the Principal) when Management does."""
    student = await q.require_student(tx, student_id)
    cls = await q.require_class(tx, class_id)
    if await q.active_in_class(tx, student.id, cls["id"]):
        raise q.already_enrolled(student)
    other = await q.active_in_period(tx, student.id, Period(cls["period"]))
    if other is not None:
        raise q.period_conflict(student, other)
    if await q.seats_taken(tx, cls["id"]) >= cls["capacity"]:
        raise DomainError("CLASS_FULL", "That class is already full.")
    approved = actor.is_principal
    status = EnrollmentStatus.APPROVED if approved else EnrollmentStatus.PENDING
    enrollment_id = await q.upsert_enrollment(
        tx,
        student_id=student.id,
        cls=cls,
        status=status,
        source=EnrollmentSource.STAFF,
        created_by=actor.id,
        decided_by=actor.id if approved else None,
        decided_at=clock.utcnow() if approved else None,
    )
    if enrollment_id is None:
        raise q.already_enrolled(student)
    await q.delete_waitlist_entry(tx, student.id, cls["id"])
    if approved:
        tx.email(
            student.family_email,
            "enrollment_approved",
            student_name=student.name,
            class_name=cls["name"],
            period_label=Period(cls["period"]).label,
        )
    tx.audit(
        actor,
        "enrollment.staff_added",
        "enrollment",
        enrollment_id,
        student_id=student.id,
        class_id=cls["id"],
        status=status.value,
    )
    return enrollment_id, status


async def _load_enrollment(tx: EngineTx, enrollment_id: int):
    row = (
        (
            await tx.session.execute(
                select(enrollments_t, classes_t.c.name.label("class_name"), classes_t.c.capacity)
                .join(classes_t, classes_t.c.id == enrollments_t.c.class_id)
                .where(enrollments_t.c.id == enrollment_id)
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise not_found("Enrollment")
    return row


async def drop(tx: EngineTx, actor: Actor, enrollment_id: int, *, as_staff: bool) -> None:
    """Family drops their child's enrollment (or dismisses a rejected one); staff remove anyone."""
    e = await _load_enrollment(tx, enrollment_id)
    student = await q.require_student(tx, e["student_id"], actor=None if as_staff else actor)
    await tx.session.execute(delete(enrollments_t).where(enrollments_t.c.id == e["id"]))
    was_active = e["status"] in ACTIVE_STATUSES
    if was_active:
        await promote(tx, [e["class_id"]])
    if as_staff and was_active:
        tx.email(
            student.family_email,
            "enrollment_removed",
            student_name=student.name,
            class_name=e["class_name"],
            period_label=Period(e["period"]).label,
        )
    tx.audit(
        actor,
        "enrollment.removed" if as_staff else "enrollment.dropped",
        "enrollment",
        e["id"],
        student_id=student.id,
        class_id=e["class_id"],
        status=EnrollmentStatus(e["status"]).value,
    )


async def approve(tx: EngineTx, actor: Actor, enrollment_id: int) -> None:
    e = await _load_enrollment(tx, enrollment_id)
    if e["status"] == EnrollmentStatus.APPROVED:
        return
    student = await q.require_student(tx, e["student_id"])
    if e["status"] == EnrollmentStatus.REJECTED:
        # Re-approving a rejected request needs the seat and the period slot to be free again.
        other = await q.active_in_period(tx, student.id, Period(e["period"]))
        if other is not None:
            raise q.period_conflict(student, other)
        if await q.seats_taken(tx, e["class_id"]) >= e["capacity"]:
            raise DomainError("CLASS_FULL", "That class has filled up since this request was rejected.")
        await q.delete_waitlist_entry(tx, student.id, e["class_id"])
    await tx.session.execute(
        update(enrollments_t)
        .where(enrollments_t.c.id == e["id"])
        .values(
            status=EnrollmentStatus.APPROVED,
            decided_by=actor.id,
            decided_at=clock.utcnow(),
            rejection_reason=None,
            updated_at=clock.utcnow(),
        )
    )
    tx.email(
        student.family_email,
        "enrollment_approved",
        student_name=student.name,
        class_name=e["class_name"],
        period_label=Period(e["period"]).label,
    )
    tx.audit(actor, "enrollment.approved", "enrollment", e["id"], student_id=student.id, class_id=e["class_id"])


async def reject(tx: EngineTx, actor: Actor, enrollment_id: int, reason: str | None) -> None:
    e = await _load_enrollment(tx, enrollment_id)
    if e["status"] == EnrollmentStatus.REJECTED:
        return
    student = await q.require_student(tx, e["student_id"])
    await tx.session.execute(
        update(enrollments_t)
        .where(enrollments_t.c.id == e["id"])
        .values(
            status=EnrollmentStatus.REJECTED,
            decided_by=actor.id,
            decided_at=clock.utcnow(),
            rejection_reason=reason,
            updated_at=clock.utcnow(),
        )
    )
    await promote(tx, [e["class_id"]])
    tx.email(
        student.family_email,
        "enrollment_rejected",
        student_name=student.name,
        class_name=e["class_name"],
        period_label=Period(e["period"]).label,
        reason=reason,
    )
    tx.audit(
        actor,
        "enrollment.rejected",
        "enrollment",
        e["id"],
        student_id=student.id,
        class_id=e["class_id"],
        reason=reason,
    )


@dataclass
class BulkResult:
    approved: list[int] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)


async def approve_many(tx: EngineTx, actor: Actor, enrollment_ids: list[int]) -> BulkResult:
    """Approves each id independently; failures are reported without undoing the others.
    (Every check in `approve` runs before it writes, so a failed id leaves no partial change.)"""
    result = BulkResult()
    for enrollment_id in dict.fromkeys(enrollment_ids):
        try:
            await approve(tx, actor, enrollment_id)
        except DomainError as exc:
            result.failed.append({"id": enrollment_id, "code": exc.code, "message": exc.message})
        else:
            result.approved.append(enrollment_id)
    return result
