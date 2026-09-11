from sqlalchemy import Subquery, func, select

from app.models import enrollments_t, waitlist_t
from app.models.enums import ACTIVE_STATUSES
from app.models.user import teacher_label


def seat_counts() -> Subquery:
    return (
        select(enrollments_t.c.class_id, func.count().label("n"))
        .where(enrollments_t.c.status.in_(ACTIVE_STATUSES))
        .group_by(enrollments_t.c.class_id)
        .subquery("seat_counts")
    )


def waitlist_counts() -> Subquery:
    return (
        select(waitlist_t.c.class_id, func.count().label("n"))
        .group_by(waitlist_t.c.class_id)
        .subquery("waitlist_counts")
    )


def ranked_waitlist() -> Subquery:
    """Every waitlist entry with its place in line: priority 1→3, then unranked, ties by join order."""
    order = (waitlist_t.c.priority.asc().nulls_last(), waitlist_t.c.id)
    return select(
        waitlist_t.c.id,
        waitlist_t.c.student_id,
        waitlist_t.c.class_id,
        waitlist_t.c.priority,
        waitlist_t.c.created_at,
        func.row_number().over(partition_by=waitlist_t.c.class_id, order_by=order).label("position"),
        func.count().over(partition_by=waitlist_t.c.class_id).label("size"),
    ).subquery("ranked_waitlist")


def teacher_ref(
    teacher_id: int | None, first_name: str | None, last_name: str | None, display_name: str | None
) -> dict | None:
    if teacher_id is None:
        return None
    return {"id": teacher_id, "label": teacher_label(first_name or "", last_name or "", display_name)}


def seat_fields(capacity: int, seats_taken: int, waitlist_count: int) -> dict:
    return {
        "capacity": capacity,
        "seats_taken": seats_taken,
        "seats_available": max(0, capacity - seats_taken),
        "is_full": seats_taken >= capacity,
        "waitlist_count": waitlist_count,
    }
