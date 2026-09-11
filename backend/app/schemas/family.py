from datetime import datetime
from typing import Literal

from app.models.enums import EnrollmentStatus, Period
from app.schemas.common import Name, Schema


class StudentIn(Schema):
    first_name: Name
    last_name: Name


class StudentUpdateIn(Schema):
    first_name: Name | None = None
    last_name: Name | None = None


class StudentOut(Schema):
    id: int
    first_name: str
    last_name: str
    created_at: datetime


class FamilyEnrollmentOut(Schema):
    id: int
    class_id: int
    class_name: str
    period: Period
    status: EnrollmentStatus
    rejection_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class FamilyWaitlistOut(Schema):
    id: int
    class_id: int
    class_name: str
    period: Period
    priority: int | None
    position: int
    size: int
    created_at: datetime


class StudentOverviewOut(StudentOut):
    enrollments: list[FamilyEnrollmentOut]
    waitlist: list[FamilyWaitlistOut]


class OverviewOut(Schema):
    students: list[StudentOverviewOut]


class EnrollmentCreateIn(Schema):
    student_id: int
    class_id: int


class EnrollmentCreatedOut(Schema):
    id: int
    status: EnrollmentStatus


class WaitlistCreateIn(Schema):
    student_id: int
    class_id: int


class WaitlistCreatedOut(Schema):
    id: int


class WaitlistPriorityIn(Schema):
    priority: Literal[1, 2, 3] | None
