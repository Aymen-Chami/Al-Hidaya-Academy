"""Public class list: published classes with seat counts — never children's names."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import classes_t, users_t
from app.services.queries.common import seat_counts, seat_fields, teacher_ref, waitlist_counts


async def list_published_classes(session: AsyncSession, *, class_id: int | None = None) -> list[dict]:
    seats, waits = seat_counts(), waitlist_counts()
    stmt = (
        select(
            classes_t.c.id,
            classes_t.c.name,
            classes_t.c.description,
            classes_t.c.period,
            classes_t.c.capacity,
            classes_t.c.teacher_id,
            users_t.c.first_name,
            users_t.c.last_name,
            users_t.c.display_name,
            func.coalesce(seats.c.n, 0).label("seats_taken"),
            func.coalesce(waits.c.n, 0).label("waitlist_count"),
        )
        .select_from(
            classes_t.outerjoin(users_t, users_t.c.id == classes_t.c.teacher_id)
            .outerjoin(seats, seats.c.class_id == classes_t.c.id)
            .outerjoin(waits, waits.c.class_id == classes_t.c.id)
        )
        .where(classes_t.c.published.is_(True))
        .order_by(classes_t.c.period, classes_t.c.sort_order, classes_t.c.id)
    )
    if class_id is not None:
        stmt = stmt.where(classes_t.c.id == class_id)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "period": r.period,
            "teacher": teacher_ref(r.teacher_id, r.first_name, r.last_name, r.display_name),
            **seat_fields(r.capacity, r.seats_taken, r.waitlist_count),
        }
        for r in rows
    ]
