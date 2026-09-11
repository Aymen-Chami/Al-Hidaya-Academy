from enum import StrEnum

import sqlalchemy as sa


class Role(StrEnum):
    FAMILY = "family"
    TEACHER = "teacher"
    MANAGEMENT = "management"
    PRINCIPAL = "principal"


ADMIN_ROLES = frozenset({Role.MANAGEMENT, Role.PRINCIPAL})
PRINCIPAL_ROLES = frozenset({Role.PRINCIPAL})
TEACHER_ROLES = frozenset({Role.TEACHER})
# Who may be assigned as a class's teacher (only Role.TEACHER may self-claim).
CAN_TEACH_ROLES = frozenset({Role.TEACHER, Role.MANAGEMENT, Role.PRINCIPAL})


class Period(StrEnum):
    ONE = "1"
    TWO = "2"
    THREE = "3"
    # "All Periods": a year-long bucket that doesn't compete with the regular periods.
    YEAR = "year"

    @property
    def label(self) -> str:
        return "All Periods" if self is Period.YEAR else f"Period {self.value}"


class EnrollmentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Statuses that hold a seat and count toward the one-class-per-period rule.
ACTIVE_STATUSES = (EnrollmentStatus.PENDING, EnrollmentStatus.APPROVED)


class EnrollmentSource(StrEnum):
    FAMILY = "family"
    STAFF = "staff"
    WAITLIST = "waitlist"


class CodePurpose(StrEnum):
    SIGNUP = "signup"
    PASSWORD_RESET = "password_reset"  # noqa: S105 — not a secret


def db_enum(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """VARCHAR + named CHECK constraint (not a native PG enum), storing the enum *values*."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
