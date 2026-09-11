"""The enrollment approval workflow. Management can see the queue; only the Principal decides."""

from fastapi import APIRouter

from app.api.deps import AdminUser, PrincipalUser, SessionDep, actor
from app.core.errors import not_found
from app.models.enums import EnrollmentStatus, Period
from app.schemas.admin import BulkApproveIn, BulkApproveOut, EnrollmentQueueItem, RejectIn
from app.services.engine import enrollments
from app.services.engine.tx import engine_tx
from app.services.queries import admin

router = APIRouter(prefix="/admin/enrollments", tags=["admin: approvals"])


async def _item(session, enrollment_id: int) -> EnrollmentQueueItem:
    rows = await admin.enrollment_queue(session, enrollment_ids=[enrollment_id])
    if not rows:
        raise not_found("Enrollment")
    return EnrollmentQueueItem.model_validate(rows[0])


@router.get("")
async def list_enrollments(
    user: AdminUser,
    session: SessionDep,
    status: EnrollmentStatus | None = None,
    class_id: int | None = None,
    period: Period | None = None,
) -> list[EnrollmentQueueItem]:
    """Oldest first. Use ?status=pending for the approval queue; includes family contact details
    for cross-checking against the registration/payment records."""
    rows = await admin.enrollment_queue(session, status=status, class_id=class_id, period=period)
    return [EnrollmentQueueItem.model_validate(r) for r in rows]


@router.post("/approve-bulk")
async def approve_bulk(body: BulkApproveIn, user: PrincipalUser) -> BulkApproveOut:
    async with engine_tx() as tx:
        result = await enrollments.approve_many(tx, actor(user), body.ids)
    return BulkApproveOut.model_validate(result)


@router.post("/{enrollment_id}/approve")
async def approve(enrollment_id: int, user: PrincipalUser, session: SessionDep) -> EnrollmentQueueItem:
    async with engine_tx() as tx:
        await enrollments.approve(tx, actor(user), enrollment_id)
    return await _item(session, enrollment_id)


@router.post("/{enrollment_id}/reject")
async def reject(enrollment_id: int, body: RejectIn, user: PrincipalUser, session: SessionDep) -> EnrollmentQueueItem:
    """Rejecting frees the seat (the waitlist moves up). The family may re-apply later."""
    async with engine_tx() as tx:
        await enrollments.reject(tx, actor(user), enrollment_id, body.reason)
    return await _item(session, enrollment_id)
