"""Class setup and roster management — Management and Principal."""

from fastapi import APIRouter, status

from app.api.deps import AdminUser, SessionDep, actor
from app.core.errors import not_found
from app.schemas.admin import (
    AdminClassOut,
    ClassCreateIn,
    ClassUpdateIn,
    MoveIn,
    StaffEnrollIn,
    StaffEnrollOut,
    TeacherAssignIn,
)
from app.services.engine import classes, enrollments, waitlist
from app.services.engine.tx import engine_tx
from app.services.queries import admin

router = APIRouter(prefix="/admin", tags=["admin: classes"])


async def _class_out(session, class_id: int) -> AdminClassOut:
    rows = await admin.admin_classes(session, class_id=class_id)
    if not rows:
        raise not_found("Class")
    return AdminClassOut.model_validate(rows[0])


@router.get("/classes")
async def list_classes(user: AdminUser, session: SessionDep) -> list[AdminClassOut]:
    """Every class incl. drafts, with rosters (status + family contact) and ranked waitlists."""
    return [AdminClassOut.model_validate(c) for c in await admin.admin_classes(session)]


@router.post("/classes", status_code=status.HTTP_201_CREATED)
async def create_class(body: ClassCreateIn, user: AdminUser, session: SessionDep) -> AdminClassOut:
    async with engine_tx() as tx:
        class_id = await classes.create_class(tx, actor(user), **body.model_dump())
    return await _class_out(session, class_id)


@router.get("/classes/{class_id}")
async def get_class(class_id: int, user: AdminUser, session: SessionDep) -> AdminClassOut:
    return await _class_out(session, class_id)


@router.patch("/classes/{class_id}")
async def update_class(class_id: int, body: ClassUpdateIn, user: AdminUser, session: SessionDep) -> AdminClassOut:
    """Only sent fields change. Raising capacity fills seats from the waitlist; lowering it below
    the seats already held, or moving to a period where someone would be double-booked, is refused."""
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "description", "period", "capacity", "published"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    async with engine_tx() as tx:
        await classes.update_class(tx, actor(user), class_id, changes)
    return await _class_out(session, class_id)


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: int, user: AdminUser) -> None:
    """Deletes the class with its enrollments and waitlist; affected families are emailed."""
    async with engine_tx() as tx:
        await classes.delete_class(tx, actor(user), class_id)


@router.post("/classes/{class_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_class(class_id: int, body: MoveIn, user: AdminUser) -> None:
    """Move up/down among classes of the same period and publish state."""
    async with engine_tx() as tx:
        await classes.move_class(tx, actor(user), class_id, body.direction)


@router.put("/classes/{class_id}/teacher")
async def assign_teacher(class_id: int, body: TeacherAssignIn, user: AdminUser, session: SessionDep) -> AdminClassOut:
    """Assign a teacher. Staff assignments are locked: the teacher can't drop the class themselves."""
    async with engine_tx() as tx:
        await classes.update_class(tx, actor(user), class_id, {"teacher_id": body.teacher_id})
    return await _class_out(session, class_id)


@router.delete("/classes/{class_id}/teacher")
async def unassign_teacher(class_id: int, user: AdminUser, session: SessionDep) -> AdminClassOut:
    async with engine_tx() as tx:
        await classes.update_class(tx, actor(user), class_id, {"teacher_id": None})
    return await _class_out(session, class_id)


@router.post("/classes/{class_id}/enrollments", status_code=status.HTTP_201_CREATED)
async def add_student_to_class(class_id: int, body: StaffEnrollIn, user: AdminUser) -> StaffEnrollOut:
    """Add a child directly (same capacity and period checks). Approved if the Principal does it,
    otherwise Pending until the Principal approves."""
    async with engine_tx() as tx:
        enrollment_id, enrollment_status = await enrollments.staff_enroll(
            tx, actor(user), class_id=class_id, student_id=body.student_id
        )
    return StaffEnrollOut(id=enrollment_id, status=enrollment_status)


@router.delete("/enrollments/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_enrollment(enrollment_id: int, user: AdminUser) -> None:
    """Remove a child from a class (the family is emailed; the seat goes to the waitlist)."""
    async with engine_tx() as tx:
        await enrollments.drop(tx, actor(user), enrollment_id, as_staff=True)


@router.delete("/waitlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_waitlist_entry(entry_id: int, user: AdminUser) -> None:
    async with engine_tx() as tx:
        await waitlist.leave(tx, actor(user), entry_id, as_staff=True)
