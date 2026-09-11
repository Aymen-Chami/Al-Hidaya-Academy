from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import EnrollmentSource, EnrollmentStatus, Period, db_enum


class Enrollment(Base):
    """A child's seat request in a class. Pending and approved both hold the seat."""

    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    class_id: Mapped[int] = mapped_column(BigInteger)
    # Copy of classes.period, kept in sync by the composite FK (ON UPDATE CASCADE), so the
    # one-active-class-per-period rule can be a unique index.
    period: Mapped[Period] = mapped_column(db_enum(Period, "enrollment_period"))
    status: Mapped[EnrollmentStatus] = mapped_column(db_enum(EnrollmentStatus, "enrollment_status"))
    source: Mapped[EnrollmentSource] = mapped_column(db_enum(EnrollmentSource, "enrollment_source"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None]
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["class_id", "period"],
            ["classes.id", "classes.period"],
            name="fk_enrollments_class_period",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        # One row per (student, class): re-applying after a rejection reuses the row.
        UniqueConstraint("student_id", "class_id"),
        Index(
            "uq_enrollments_student_period_active",
            "student_id",
            "period",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
        Index("ix_enrollments_class_status", "class_id", "status"),
        Index("ix_enrollments_status_created", "status", "created_at"),
    )


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    # 1st / 2nd / 3rd choice, or NULL for unranked. Unique per student across their entries.
    priority: Mapped[int | None] = mapped_column(SmallInteger)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "class_id"),
        CheckConstraint("priority IS NULL OR priority BETWEEN 1 AND 3", name="priority_range"),
        Index(
            "uq_waitlist_entries_student_priority",
            "student_id",
            "priority",
            unique=True,
            postgresql_where=text("priority IS NOT NULL"),
        ),
        # Queue order: priority first (NULLs sort last ascending), then join order.
        Index("ix_waitlist_entries_queue", "class_id", "priority", "id"),
    )
