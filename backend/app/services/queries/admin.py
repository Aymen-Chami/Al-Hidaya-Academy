"""Staff views (Management + Principal): every class incl. drafts, rosters, waitlists, people."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import audit_t, classes_t, enrollments_t, students_t, users_t
from app.models.enums import ACTIVE_STATUSES, EnrollmentStatus, Period, Role
from app.services.queries.common import ranked_waitlist, seat_counts, seat_fields, teacher_ref, waitlist_counts


def _family(row, prefix: str = "family_") -> dict | None:
    if row[f"{prefix}id"] is None:
        return None
    return {
        "id": row[f"{prefix}id"],
        "first_name": row[f"{prefix}first_name"],
        "last_name": row[f"{prefix}last_name"],
        "email": row[f"{prefix}email"],
        "phone": row[f"{prefix}phone"],
    }


def _family_columns(alias):
    return (
        alias.c.id.label("family_id"),
        alias.c.first_name.label("family_first_name"),
        alias.c.last_name.label("family_last_name"),
        alias.c.email.label("family_email"),
        alias.c.phone.label("family_phone"),
    )


async def admin_classes(session: AsyncSession, *, class_id: int | None = None) -> list[dict]:
    seats, waits = seat_counts(), waitlist_counts()
    teacher = users_t.alias("teacher")
    stmt = (
        select(
            classes_t,
            teacher.c.first_name.label("t_first_name"),
            teacher.c.last_name.label("t_last_name"),
            teacher.c.display_name.label("t_display_name"),
            teacher.c.email.label("t_email"),
            func.coalesce(seats.c.n, 0).label("seats_taken"),
            func.coalesce(waits.c.n, 0).label("waitlist_count"),
        )
        .select_from(
            classes_t.outerjoin(teacher, teacher.c.id == classes_t.c.teacher_id)
            .outerjoin(seats, seats.c.class_id == classes_t.c.id)
            .outerjoin(waits, waits.c.class_id == classes_t.c.id)
        )
        # Per period: drafts first, then published, each in manual sort order (as in the prototype).
        .order_by(classes_t.c.period, classes_t.c.published, classes_t.c.sort_order, classes_t.c.id)
    )
    if class_id is not None:
        stmt = stmt.where(classes_t.c.id == class_id)
    classes = (await session.execute(stmt)).mappings().all()
    if not classes:
        return []
    ids = [c["id"] for c in classes]
    family = users_t.alias("family")

    roster = (
        (
            await session.execute(
                select(
                    enrollments_t.c.id.label("enrollment_id"),
                    enrollments_t.c.class_id,
                    enrollments_t.c.status,
                    enrollments_t.c.source,
                    enrollments_t.c.created_at,
                    students_t.c.id.label("student_id"),
                    students_t.c.first_name,
                    students_t.c.last_name,
                    *_family_columns(family),
                )
                .join(students_t, students_t.c.id == enrollments_t.c.student_id)
                .outerjoin(family, family.c.id == students_t.c.family_id)
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
                    ranked.c.id.label("entry_id"),
                    ranked.c.class_id,
                    ranked.c.priority,
                    ranked.c.position,
                    ranked.c.created_at,
                    students_t.c.id.label("student_id"),
                    students_t.c.first_name,
                    students_t.c.last_name,
                    *_family_columns(family),
                )
                .join(students_t, students_t.c.id == ranked.c.student_id)
                .outerjoin(family, family.c.id == students_t.c.family_id)
                .where(ranked.c.class_id.in_(ids))
                .order_by(ranked.c.class_id, ranked.c.position)
            )
        )
        .mappings()
        .all()
    )

    out = {}
    for c in classes:
        ref = teacher_ref(c["teacher_id"], c["t_first_name"], c["t_last_name"], c["t_display_name"])
        if ref is not None:
            ref["email"] = c["t_email"]
        out[c["id"]] = {
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "period": c["period"],
            "published": c["published"],
            "sort_order": c["sort_order"],
            "teacher": ref,
            "teacher_locked": c["teacher_locked"],
            **seat_fields(c["capacity"], c["seats_taken"], c["waitlist_count"]),
            "roster": [],
            "waitlist": [],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
        }
    for r in roster:
        out[r["class_id"]]["roster"].append(
            {
                "enrollment_id": r["enrollment_id"],
                "student_id": r["student_id"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "status": r["status"],
                "source": r["source"],
                "created_at": r["created_at"],
                "family": _family(r),
            }
        )
    for w in waitlist:
        out[w["class_id"]]["waitlist"].append(
            {
                "entry_id": w["entry_id"],
                "student_id": w["student_id"],
                "first_name": w["first_name"],
                "last_name": w["last_name"],
                "priority": w["priority"],
                "position": w["position"],
                "created_at": w["created_at"],
                "family": _family(w),
            }
        )
    return list(out.values())


async def enrollment_queue(
    session: AsyncSession,
    *,
    status: EnrollmentStatus | None = None,
    class_id: int | None = None,
    period: Period | None = None,
    enrollment_ids: list[int] | None = None,
) -> list[dict]:
    """The approval queue: enrollments with the child, class and family contact for cross-checking."""
    family = users_t.alias("family")
    decider = users_t.alias("decider")
    stmt = (
        select(
            enrollments_t.c.id,
            enrollments_t.c.status,
            enrollments_t.c.source,
            enrollments_t.c.period,
            enrollments_t.c.rejection_reason,
            enrollments_t.c.created_at,
            enrollments_t.c.decided_at,
            classes_t.c.id.label("class_id"),
            classes_t.c.name.label("class_name"),
            students_t.c.id.label("student_id"),
            students_t.c.first_name,
            students_t.c.last_name,
            decider.c.id.label("decided_by_id"),
            decider.c.first_name.label("decided_by_first_name"),
            decider.c.last_name.label("decided_by_last_name"),
            *_family_columns(family),
        )
        .join(classes_t, classes_t.c.id == enrollments_t.c.class_id)
        .join(students_t, students_t.c.id == enrollments_t.c.student_id)
        .outerjoin(family, family.c.id == students_t.c.family_id)
        .outerjoin(decider, decider.c.id == enrollments_t.c.decided_by)
        .order_by(enrollments_t.c.created_at, enrollments_t.c.id)
    )
    if status is not None:
        stmt = stmt.where(enrollments_t.c.status == status)
    if class_id is not None:
        stmt = stmt.where(enrollments_t.c.class_id == class_id)
    if period is not None:
        stmt = stmt.where(enrollments_t.c.period == period)
    if enrollment_ids is not None:
        stmt = stmt.where(enrollments_t.c.id.in_(enrollment_ids))
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "source": r["source"],
            "period": r["period"],
            "rejection_reason": r["rejection_reason"],
            "created_at": r["created_at"],
            "decided_at": r["decided_at"],
            "class_id": r["class_id"],
            "class_name": r["class_name"],
            "student": {"id": r["student_id"], "first_name": r["first_name"], "last_name": r["last_name"]},
            "family": _family(r),
            "decided_by": (
                {"id": r["decided_by_id"], "name": f"{r['decided_by_first_name']} {r['decided_by_last_name']}"}
                if r["decided_by_id"]
                else None
            ),
        }
        for r in rows
    ]


async def list_students(
    session: AsyncSession, *, q: str | None = None, family_id: int | None = None, student_id: int | None = None
) -> list[dict]:
    family = users_t.alias("family")
    active = (
        select(enrollments_t.c.student_id, func.count().label("n"))
        .where(enrollments_t.c.status.in_(ACTIVE_STATUSES))
        .group_by(enrollments_t.c.student_id)
        .subquery()
    )
    stmt = (
        select(
            students_t.c.id,
            students_t.c.first_name,
            students_t.c.last_name,
            students_t.c.created_at,
            func.coalesce(active.c.n, 0).label("active_enrollments"),
            *_family_columns(family),
        )
        .select_from(
            students_t.outerjoin(family, family.c.id == students_t.c.family_id).outerjoin(
                active, active.c.student_id == students_t.c.id
            )
        )
        .order_by(students_t.c.last_name, students_t.c.first_name, students_t.c.id)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                (students_t.c.first_name + " " + students_t.c.last_name).ilike(like),
                family.c.email.ilike(like),
            )
        )
    if family_id is not None:
        stmt = stmt.where(students_t.c.family_id == family_id)
    if student_id is not None:
        stmt = stmt.where(students_t.c.id == student_id)
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": r["id"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "created_at": r["created_at"],
            "active_enrollments": r["active_enrollments"],
            "family": _family(r),
        }
        for r in rows
    ]


async def list_users(
    session: AsyncSession, *, role: Role | None = None, q: str | None = None, user_id: int | None = None
) -> list[dict]:
    stmt = select(users_t).order_by(users_t.c.last_name, users_t.c.first_name, users_t.c.id)
    if role is not None:
        stmt = stmt.where(users_t.c.role == role)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_((users_t.c.first_name + " " + users_t.c.last_name).ilike(like), users_t.c.email.ilike(like))
        )
    if user_id is not None:
        stmt = stmt.where(users_t.c.id == user_id)
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "display_name": r["display_name"],
            "phone": r["phone"],
            "role": r["role"],
            "is_active": r["is_active"],
            "activated": r["password_hash"] is not None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def list_audit(session: AsyncSession, *, limit: int, before_id: int | None) -> list[dict]:
    actor = users_t.alias("actor")
    stmt = (
        select(audit_t, actor.c.first_name, actor.c.last_name)
        .outerjoin(actor, actor.c.id == audit_t.c.actor_id)
        .order_by(audit_t.c.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(audit_t.c.id < before_id)
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": r["id"],
            "actor": {"id": r["actor_id"], "name": f"{r['first_name']} {r['last_name']}"} if r["actor_id"] else None,
            "action": r["action"],
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "details": r["details"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
