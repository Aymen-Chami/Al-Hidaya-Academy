"""What a family sees: their children, each child's enrollments (with status) and waitlist places."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import classes_t, enrollments_t, students_t
from app.services.queries.common import ranked_waitlist


async def list_students(session: AsyncSession, family_id: int) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(students_t.c.id, students_t.c.first_name, students_t.c.last_name, students_t.c.created_at)
                .where(students_t.c.family_id == family_id)
                .order_by(students_t.c.id)
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def overview(session: AsyncSession, family_id: int) -> list[dict]:
    students = await list_students(session, family_id)
    if not students:
        return []
    ids = [s["id"] for s in students]

    enrollment_rows = (
        (
            await session.execute(
                select(
                    enrollments_t.c.id,
                    enrollments_t.c.student_id,
                    enrollments_t.c.class_id,
                    classes_t.c.name.label("class_name"),
                    enrollments_t.c.period,
                    enrollments_t.c.status,
                    enrollments_t.c.rejection_reason,
                    enrollments_t.c.created_at,
                    enrollments_t.c.decided_at,
                )
                .join(classes_t, classes_t.c.id == enrollments_t.c.class_id)
                .where(enrollments_t.c.student_id.in_(ids))
                .order_by(enrollments_t.c.period, enrollments_t.c.id)
            )
        )
        .mappings()
        .all()
    )

    ranked = ranked_waitlist()
    waitlist_rows = (
        (
            await session.execute(
                select(
                    ranked.c.id,
                    ranked.c.student_id,
                    ranked.c.class_id,
                    classes_t.c.name.label("class_name"),
                    classes_t.c.period,
                    ranked.c.priority,
                    ranked.c.position,
                    ranked.c.size,
                    ranked.c.created_at,
                )
                .join(classes_t, classes_t.c.id == ranked.c.class_id)
                .where(ranked.c.student_id.in_(ids))
                .order_by(classes_t.c.period, ranked.c.priority.asc().nulls_last(), ranked.c.id)
            )
        )
        .mappings()
        .all()
    )

    by_student = {s["id"]: {**s, "enrollments": [], "waitlist": []} for s in students}
    for e in enrollment_rows:
        by_student[e["student_id"]]["enrollments"].append(dict(e))
    for w in waitlist_rows:
        by_student[w["student_id"]]["waitlist"].append(dict(w))
    return list(by_student.values())
