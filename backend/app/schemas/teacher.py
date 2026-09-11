from app.models.enums import EnrollmentStatus, Period
from app.schemas.common import Schema
from app.schemas.public import SeatInfo


class TeacherRosterEntry(Schema):
    student_id: int
    first_name: str
    last_name: str
    status: EnrollmentStatus


class TeacherWaitlistEntry(Schema):
    student_id: int
    first_name: str
    last_name: str
    priority: int | None
    position: int


class TeacherClassOut(SeatInfo):
    id: int
    name: str
    description: str
    period: Period
    published: bool
    teacher_locked: bool
    roster: list[TeacherRosterEntry]
    waitlist: list[TeacherWaitlistEntry]
