"""A teacher's own classes (drafts included) with roster and waitlist — no family contact details."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import classes_t, enrollments_t, students_t
from app.models.enums import ACTIVE_STATUSES
from app.services.queries.common import ranked_waitlist, seat_counts, seat_fields, waitlist_counts


async def teacher_classes(session: AsyncSession, teacher_id: int) -> list[dict]:
    seats, waits = seat_counts(), waitlist_counts()
    classes = (
        await session.execute(
            select(
                classes_t.c.id,
                classes_t.c.name,
                classes_t.c.description,
                classes_t.c.period,
                classes_t.c.capacity,
                classes_t.c.published,
                classes_t.c.teacher_locked,
                func.coalesce(seats.c.n, 0).label("seats_taken"),
                func.coalesce(waits.c.n, 0).label("waitlist_count"),
            )
            .select_from(
                classes_t.outerjoin(seats, seats.c.class_id == classes_t.c.id).outerjoin(
                    waits, waits.c.class_id == classes_t.c.id
                )
            )
            .where(classes_t.c.teacher_id == teacher_id)
            .order_by(classes_t.c.period, classes_t.c.sort_order, classes_t.c.id)
        )
    ).all()
    if not classes:
        return []
    ids = [c.id for c in classes]

    roster = (
        (
            await session.execute(
                select(
                    enrollments_t.c.class_id,
                    enrollments_t.c.status,
                    students_t.c.id.label("student_id"),
                    students_t.c.first_name,
                    students_t.c.last_name,
                )
                .join(students_t, students_t.c.id == enrollments_t.c.student_id)
                .where(enrollments_t.c.class_id.in_(ids), enrollments_t.c.status.in_(ACTIVE_STATUSES))
                .order_by(students_t.c.last_name, students_t.c.first_name)
            )
        )
        .mappings()
        .all()
    )

    ranked = ranked_waitlist()
    waitlist = (
        (
            await session.execute(
                select(
                    ranked.c.class_id,
                    ranked.c.priority,
                    ranked.c.position,
                    students_t.c.id.label("student_id"),
                    students_t.c.first_name,
                    students_t.c.last_name,
                )
                .join(students_t, students_t.c.id == ranked.c.student_id)
                .where(ranked.c.class_id.in_(ids))
                .order_by(ranked.c.class_id, ranked.c.position)
            )
        )
        .mappings()
        .all()
    )

    out = {
        c.id: {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "period": c.period,
            "published": c.published,
            "teacher_locked": c.teacher_locked,
            **seat_fields(c.capacity, c.seats_taken, c.waitlist_count),
            "roster": [],
            "waitlist": [],
        }
        for c in classes
    }
    for r in roster:
        out[r["class_id"]]["roster"].append({k: r[k] for k in ("student_id", "first_name", "last_name", "status")})
    for w in waitlist:
        out[w["class_id"]]["waitlist"].append(
            {k: w[k] for k in ("student_id", "first_name", "last_name", "priority", "position")}
        )
    return list(out.values())
