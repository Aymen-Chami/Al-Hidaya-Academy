from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from app.models.enums import EnrollmentSource, EnrollmentStatus, Period, Role
from app.schemas.common import Email, Name, OptionalText80, Phone, Schema, TeacherRef
from app.schemas.public import SeatInfo

ClassName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Capacity = Annotated[int, Field(ge=1, le=500)]


class FamilyContact(Schema):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str | None


class AdminTeacherRef(TeacherRef):
    email: str


class AdminRosterEntry(Schema):
    enrollment_id: int
    student_id: int
    first_name: str
    last_name: str
    status: EnrollmentStatus
    source: EnrollmentSource
    created_at: datetime
    family: FamilyContact | None


class AdminWaitlistEntry(Schema):
    entry_id: int
    student_id: int
    first_name: str
    last_name: str
    priority: int | None
    position: int
    created_at: datetime
    family: FamilyContact | None


class AdminClassOut(SeatInfo):
    id: int
    name: str
    description: str
    period: Period
    published: bool
    sort_order: int
    teacher: AdminTeacherRef | None
    teacher_locked: bool
    roster: list[AdminRosterEntry]
    waitlist: list[AdminWaitlistEntry]
    created_at: datetime
    updated_at: datetime


class ClassCreateIn(Schema):
    name: ClassName
    description: Description = ""
    period: Period
    capacity: Capacity = 10
    teacher_id: int | None = None
    published: bool = True


class ClassUpdateIn(Schema):
    """Only the fields you send are changed. Send "teacher_id": null to unassign the teacher."""

    name: ClassName | None = None
    description: Description | None = None
    period: Period | None = None
    capacity: Capacity | None = None
    teacher_id: int | None = None
    published: bool | None = None


class MoveIn(Schema):
    direction: Literal["up", "down"]


class TeacherAssignIn(Schema):
    teacher_id: int


class StaffEnrollIn(Schema):
    student_id: int


class StaffEnrollOut(Schema):
    id: int
    status: EnrollmentStatus


class AdminStudentIn(Schema):
    first_name: Name
    last_name: Name
    family_id: int | None = None


class AdminStudentUpdateIn(Schema):
    first_name: Name | None = None
    last_name: Name | None = None
    family_id: int | None = None


class AdminStudentOut(Schema):
    id: int
    first_name: str
    last_name: str
    created_at: datetime
    active_enrollments: int
    family: FamilyContact | None


class UserCreateIn(Schema):
    email: Email
    first_name: Name
    last_name: Name
    display_name: OptionalText80 | None = None
    phone: Phone | None = None
    role: Role
    send_invite: bool = True


class UserUpdateIn(Schema):
    first_name: Name | None = None
    last_name: Name | None = None
    display_name: OptionalText80 | None = None
    phone: Phone | None = None
    role: Role | None = None
    is_active: bool | None = None


class UserOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    display_name: str | None
    phone: str | None
    role: Role
    is_active: bool
    activated: bool
    created_at: datetime


class StudentRef(Schema):
    id: int
    first_name: str
    last_name: str


class PersonRef(Schema):
    id: int
    name: str


class EnrollmentQueueItem(Schema):
    id: int
    status: EnrollmentStatus
    source: EnrollmentSource
    period: Period
    rejection_reason: str | None
    created_at: datetime
    decided_at: datetime | None
    class_id: int
    class_name: str
    student: StudentRef
    family: FamilyContact | None
    decided_by: PersonRef | None


class RejectIn(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class BulkApproveIn(Schema):
    ids: list[int] = Field(min_length=1, max_length=200)


class BulkFailure(Schema):
    id: int
    code: str
    message: str


class BulkApproveOut(Schema):
    approved: list[int]
    failed: list[BulkFailure]


class AuditEventOut(Schema):
    id: int
    actor: PersonRef | None
    action: str
    entity_type: str
    entity_id: int | None
    details: dict[str, Any]
    created_at: datetime
