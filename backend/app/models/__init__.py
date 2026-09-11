from app.models.auth import EmailCode, UserSession
from app.models.enrollment import Enrollment, WaitlistEntry
from app.models.outbox import AuditEvent, OutboxEmail
from app.models.school_class import SchoolClass
from app.models.student import Student
from app.models.user import User

# Core table handles, used by the enrollment engine and read queries (no ORM identity map involved).
users_t = User.__table__
students_t = Student.__table__
classes_t = SchoolClass.__table__
enrollments_t = Enrollment.__table__
waitlist_t = WaitlistEntry.__table__
sessions_t = UserSession.__table__
email_codes_t = EmailCode.__table__
outbox_t = OutboxEmail.__table__
audit_t = AuditEvent.__table__

__all__ = [
    "AuditEvent",
    "EmailCode",
    "Enrollment",
    "OutboxEmail",
    "SchoolClass",
    "Student",
    "User",
    "UserSession",
    "WaitlistEntry",
    "audit_t",
    "classes_t",
    "email_codes_t",
    "enrollments_t",
    "outbox_t",
    "sessions_t",
    "students_t",
    "users_t",
    "waitlist_t",
]
