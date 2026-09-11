"""The family side: a parent manages their children and signs them up. Any account may have children."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep, actor
from app.core.errors import not_found
from app.models.enums import EnrollmentStatus
from app.schemas.family import (
    EnrollmentCreatedOut,
    EnrollmentCreateIn,
    OverviewOut,
    StudentIn,
    StudentOut,
    StudentUpdateIn,
    WaitlistCreatedOut,
    WaitlistCreateIn,
    WaitlistPriorityIn,
)
from app.services.engine import enrollments, people, waitlist
from app.services.engine.tx import engine_tx
from app.services.queries import family

router = APIRouter(tags=["family"])


async def _own_student(session, user, student_id: int) -> StudentOut:
    for s in await family.list_students(session, user.id):
        if s["id"] == student_id:
            return StudentOut.model_validate(s)
    raise not_found("Student")


@router.get("/me/students")
async def list_my_students(user: CurrentUser, session: SessionDep) -> list[StudentOut]:
    return [StudentOut.model_validate(s) for s in await family.list_students(session, user.id)]


@router.post("/me/students", status_code=status.HTTP_201_CREATED)
async def add_student(body: StudentIn, user: CurrentUser, session: SessionDep) -> StudentOut:
    async with engine_tx() as tx:
        student_id = await people.create_student(
            tx, actor(user), family_id=user.id, first_name=body.first_name, last_name=body.last_name
        )
    return await _own_student(session, user, student_id)


@router.patch("/me/students/{student_id}")
async def update_student(student_id: int, body: StudentUpdateIn, user: CurrentUser, session: SessionDep) -> StudentOut:
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    async with engine_tx() as tx:
        await people.update_student(tx, actor(user), student_id, changes, as_staff=False)
    return await _own_student(session, user, student_id)


@router.delete("/me/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_student(student_id: int, user: CurrentUser) -> None:
    """Removes the child and all their enrollments/waitlist entries (freed seats go to the waitlist)."""
    async with engine_tx() as tx:
        await people.delete_student(tx, actor(user), student_id, as_staff=False)


@router.get("/me/overview")
async def my_overview(user: CurrentUser, session: SessionDep) -> OverviewOut:
    """Each child with their enrollments (pending/approved/rejected) and waitlist places."""
    return OverviewOut.model_validate({"students": await family.overview(session, user.id)})


@router.post("/enrollments", status_code=status.HTTP_201_CREATED)
async def sign_up(body: EnrollmentCreateIn, user: CurrentUser) -> EnrollmentCreatedOut:
    """Request a seat. The enrollment starts Pending (it holds the seat) until the Principal decides."""
    async with engine_tx() as tx:
        enrollment_id = await enrollments.sign_up(tx, actor(user), student_id=body.student_id, class_id=body.class_id)
    return EnrollmentCreatedOut(id=enrollment_id, status=EnrollmentStatus.PENDING)


@router.delete("/enrollments/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def drop_enrollment(enrollment_id: int, user: CurrentUser) -> None:
    """Drop a class (or dismiss a rejected request). The freed seat goes to the waitlist."""
    async with engine_tx() as tx:
        await enrollments.drop(tx, actor(user), enrollment_id, as_staff=False)


@router.post("/waitlist", status_code=status.HTTP_201_CREATED)
async def join_waitlist(body: WaitlistCreateIn, user: CurrentUser) -> WaitlistCreatedOut:
    """Join a full class's waitlist (allowed even while holding another class in the same period)."""
    async with engine_tx() as tx:
        entry_id = await waitlist.join(tx, actor(user), student_id=body.student_id, class_id=body.class_id)
    return WaitlistCreatedOut(id=entry_id)


@router.patch("/waitlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_waitlist_priority(entry_id: int, body: WaitlistPriorityIn, user: CurrentUser) -> None:
    """Rank this entry 1st/2nd/3rd choice (or null for unranked). Clears that rank elsewhere."""
    async with engine_tx() as tx:
        await waitlist.set_priority(tx, actor(user), entry_id, body.priority)


@router.delete("/waitlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave_waitlist(entry_id: int, user: CurrentUser) -> None:
    async with engine_tx() as tx:
        await waitlist.leave(tx, actor(user), entry_id, as_staff=False)
