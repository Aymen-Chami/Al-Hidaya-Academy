from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.errors import not_found
from app.schemas.public import PublicClassOut
from app.services.queries import catalog

router = APIRouter(tags=["classes"])


@router.get("/classes")
async def list_classes(session: SessionDep) -> list[PublicClassOut]:
    """The published schedule with live seat counts. Public; never includes children's names."""
    return [PublicClassOut.model_validate(c) for c in await catalog.list_published_classes(session)]


@router.get("/classes/{class_id}")
async def get_class(class_id: int, session: SessionDep) -> PublicClassOut:
    rows = await catalog.list_published_classes(session, class_id=class_id)
    if not rows:
        raise not_found("Class")
    return PublicClassOut.model_validate(rows[0])
