"""Waitlist promotion — the server-side port of the prototype's resolveWaitlistPromotions.

When a seat opens, the top of the class's waitlist (priority 1→3, then unranked; ties by join
order) is moved in. Being on a waitlist means "I want this more than what I have", so if that
child already holds another class in the same period they are switched out of it, which frees a
seat there and may cascade. Differences from the prototype:
  * keeps filling a class until it is full or its waitlist is empty (the prototype moved one
    person per pass, so a capacity increase of +3 only promoted one),
  * an approved enrollment stays approved when the child is switched,
  * the child's same-period waitlist entries ranked below the one that got them in are removed,
    so a later opening in a lower choice can't pull them out of a higher one.
Terminates because every step deletes at least one waitlist entry and nothing adds any.
"""

import logging
from collections import deque
from collections.abc import Iterable

from sqlalchemy import delete, or_, select

from app.models import classes_t, enrollments_t, waitlist_t
from app.models.enums import EnrollmentSource, EnrollmentStatus, Period
from app.services.engine import queries as q
from app.services.engine.tx import SYSTEM, EngineTx

log = logging.getLogger(__name__)


async def _prune_lower_ranked(tx: EngineTx, student_id: int, period: Period, priority: int | None) -> list[str]:
    if priority is None:
        return []
    rows = (
        await tx.session.execute(
            select(waitlist_t.c.id, classes_t.c.name)
            .join(classes_t, classes_t.c.id == waitlist_t.c.class_id)
            .where(
                waitlist_t.c.student_id == student_id,
                classes_t.c.period == period,
                or_(waitlist_t.c.priority.is_(None), waitlist_t.c.priority > priority),
            )
            .order_by(classes_t.c.name)
        )
    ).all()
    if rows:
        await tx.session.execute(delete(waitlist_t).where(waitlist_t.c.id.in_([r.id for r in rows])))
    return [r.name for r in rows]


async def promote(tx: EngineTx, class_ids: Iterable[int]) -> int:
    """Fills free seats in the given classes (and any classes freed by switches). Returns #promotions."""
    queue = deque(dict.fromkeys(class_ids))
    promotions = 0
    while queue:
        cls = await q.get_class(tx, queue.popleft())
        if cls is None:
            continue
        period = Period(cls["period"])
        while await q.seats_taken(tx, cls["id"]) < cls["capacity"]:
            head = (
                await tx.session.execute(
                    select(waitlist_t.c.id, waitlist_t.c.student_id, waitlist_t.c.priority)
                    .where(waitlist_t.c.class_id == cls["id"])
                    .order_by(waitlist_t.c.priority.asc().nulls_last(), waitlist_t.c.id)
                    .limit(1)
                )
            ).first()
            if head is None:
                break
            await tx.session.execute(delete(waitlist_t).where(waitlist_t.c.id == head.id))
            if await q.active_in_class(tx, head.student_id, cls["id"]):
                log.warning("Waitlist entry %s was for a class the student already holds; dropped it", head.id)
                continue

            old = await q.active_in_period(tx, head.student_id, period)
            if old is not None:
                # Delete before inserting so the one-active-per-period unique index never trips.
                await tx.session.execute(delete(enrollments_t).where(enrollments_t.c.id == old["id"]))
                queue.append(old["class_id"])
            carry_approval = old is not None and old["status"] == EnrollmentStatus.APPROVED
            status = EnrollmentStatus.APPROVED if carry_approval else EnrollmentStatus.PENDING
            enrollment_id = await q.upsert_enrollment(
                tx,
                student_id=head.student_id,
                cls=cls,
                status=status,
                source=EnrollmentSource.WAITLIST,
                created_by=None,
                decided_by=old["decided_by"] if carry_approval else None,
                decided_at=old["decided_at"] if carry_approval else None,
            )
            pruned = await _prune_lower_ranked(tx, head.student_id, period, head.priority)
            promotions += 1

            student = await q.get_student(tx, head.student_id)
            tx.email(
                student.family_email if student else None,
                "waitlist_promoted",
                student_name=student.name if student else "",
                class_name=cls["name"],
                period_label=period.label,
                from_class_name=old["class_name"] if old else None,
                status=status.value,
                pruned=pruned,
            )
            tx.audit(
                SYSTEM,
                "waitlist.promoted",
                "enrollment",
                enrollment_id,
                student_id=head.student_id,
                class_id=cls["id"],
                from_class_id=old["class_id"] if old else None,
                status=status.value,
                pruned=pruned,
            )
    return promotions
