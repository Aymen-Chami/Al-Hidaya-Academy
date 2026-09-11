from app.models.enums import Period
from app.schemas.common import Schema, TeacherRef


class SeatInfo(Schema):
    capacity: int
    seats_taken: int
    seats_available: int
    is_full: bool
    waitlist_count: int


class PublicClassOut(SeatInfo):
    """Published class as anyone may see it: counts only, no children's names."""

    id: int
    name: str
    description: str
    period: Period
    teacher: TeacherRef | None
