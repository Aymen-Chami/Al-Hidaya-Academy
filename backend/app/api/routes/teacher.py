from fastapi import APIRouter, status

from app.api.deps import CanTeachUser, SessionDep, TeacherUser, actor
from app.schemas.teacher import TeacherClassOut
from app.services.engine import classes
from app.services.engine.tx import engine_tx
from app.services.queries import teacher

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/classes")
async def my_classes(user: CanTeachUser, session: SessionDep) -> list[TeacherClassOut]:
    """Classes I teach (drafts included), with roster status and waitlist. Unclaimed classes are
    in GET /classes (teacher = null)."""
    return [TeacherClassOut.model_validate(c) for c in await teacher.teacher_classes(session, user.id)]


@router.post("/classes/{class_id}/claim", status_code=status.HTTP_204_NO_CONTENT)
async def claim_class(class_id: int, user: TeacherUser) -> None:
    """Claim an unclaimed published class (one per period)."""
    async with engine_tx() as tx:
        await classes.claim(tx, actor(user), class_id)


@router.delete("/classes/{class_id}/claim", status_code=status.HTTP_204_NO_CONTENT)
async def drop_claim(class_id: int, user: TeacherUser) -> None:
    """Give up a class you claimed yourself (not one the school assigned you)."""
    async with engine_tx() as tx:
        await classes.drop_claim(tx, actor(user), class_id)
