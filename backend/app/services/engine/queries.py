"""Small Core read/write helpers shared by the engine modules (all run inside an EngineTx)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import RowMapping, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import clock
from app.core.errors import DomainError, not_found
from app.models import classes_t, enrollments_t, students_t, users_t, waitlist_t
from app.models.enums import ACTIVE_STATUSES, EnrollmentSource, EnrollmentStatus, Period
from app.services.engine.tx import Actor, EngineTx


@dataclass(frozen=True)
class StudentInfo:
    id: int
    family_id: int | None
    first_name: str
    last_name: str
    family_email: str | None

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


async def get_class(tx: EngineTx, class_id: int) -> RowMapping | None:
    return (await tx.session.execute(select(classes_t).where(classes_t.c.id == class_id))).mappings().first()


async def require_class(tx: EngineTx, class_id: int) -> RowMapping:
    cls = await get_class(tx, class_id)
    if cls is None:
        raise not_found("Class")
    return cls


async def get_student(tx: EngineTx, student_id: int) -> StudentInfo | None:
    row = (
        await tx.session.execute(
            select(
                students_t.c.id,
                students_t.c.family_id,
                students_t.c.first_name,
                students_t.c.last_name,
                users_t.c.email.label("family_email"),
            )
            .select_from(students_t.outerjoin(users_t, users_t.c.id == students_t.c.family_id))
            .where(students_t.c.id == student_id)
        )
    ).first()
    return StudentInfo(*row) if row else None


async def require_student(tx: EngineTx, student_id: int, *, actor: Actor | None = None) -> StudentInfo:
    """Loads a student; when `actor` is given, it must be the student's family (else 404)."""
    student = await get_student(tx, student_id)
    if student is None or (actor is not None and student.family_id != actor.id):
        raise not_found("Student")
    return student


async def seats_taken(tx: EngineTx, class_id: int) -> int:
    return (
        await tx.session.execute(
            select(func.count())
            .select_from(enrollments_t)
            .where(enrollments_t.c.class_id == class_id, enrollments_t.c.status.in_(ACTIVE_STATUSES))
        )
    ).scalar_one()


async def active_in_class(tx: EngineTx, student_id: int, class_id: int) -> RowMapping | None:
    return (
        (
            await tx.session.execute(
                select(enrollments_t).where(
                    enrollments_t.c.student_id == student_id,
                    enrollments_t.c.class_id == class_id,
                    enrollments_t.c.status.in_(ACTIVE_STATUSES),
                )
            )
        )
        .mappings()
        .first()
    )


async def active_in_period(tx: EngineTx, student_id: int, period: Period) -> RowMapping | None:
    """The student's pending/approved enrollment in this period bucket (at most one), with class name."""
    return (
        (
            await tx.session.execute(
                select(enrollments_t, classes_t.c.name.label("class_name"))
                .join(classes_t, classes_t.c.id == enrollments_t.c.class_id)
                .where(
                    enrollments_t.c.student_id == student_id,
                    enrollments_t.c.period == period,
                    enrollments_t.c.status.in_(ACTIVE_STATUSES),
                )
            )
        )
        .mappings()
        .first()
    )


async def delete_waitlist_entry(tx: EngineTx, student_id: int, class_id: int) -> None:
    await tx.session.execute(
        delete(waitlist_t).where(waitlist_t.c.student_id == student_id, waitlist_t.c.class_id == class_id)
    )


async def upsert_enrollment(
    tx: EngineTx,
    *,
    student_id: int,
    cls: RowMapping,
    status: EnrollmentStatus,
    source: EnrollmentSource,
    created_by: int | None,
    decided_by: int | None = None,
    decided_at: datetime | None = None,
) -> int | None:
    """Creates the (student, class) enrollment, or revives a previously rejected row.

    Returns the enrollment id, or None when an active row already exists.
    """
    now = clock.utcnow()
    stmt = pg_insert(enrollments_t).values(
        student_id=student_id,
        class_id=cls["id"],
        period=cls["period"],
        status=status,
        source=source,
        created_by=created_by,
        decided_by=decided_by,
        decided_at=decided_at,
        rejection_reason=None,
        created_at=now,
        updated_at=now,
    )
    revived = {
        col: stmt.excluded[col]
        for col in (
            "period",
            "status",
            "source",
            "created_by",
            "decided_by",
            "decided_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        )
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_enrollments_student_id_class_id",
        set_=revived,
        where=enrollments_t.c.status == EnrollmentStatus.REJECTED,
    ).returning(enrollments_t.c.id)
    return (await tx.session.execute(stmt)).scalar_one_or_none()


def period_conflict(student: StudentInfo, other: RowMapping) -> DomainError:
    period = Period(other["period"])
    return DomainError(
        "PERIOD_CONFLICT",
        f"{student.name} already has a {period.label} class ({other['class_name']}). Drop it first.",
        details={"class_id": other["class_id"], "class_name": other["class_name"]},
    )


def class_full() -> DomainError:
    return DomainError("CLASS_FULL", "That class is full — join the waitlist instead.")


def already_enrolled(student: StudentInfo) -> DomainError:
    return DomainError("ALREADY_ENROLLED", f"{student.name} is already signed up for this class.")
