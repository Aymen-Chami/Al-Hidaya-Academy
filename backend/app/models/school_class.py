from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Period, db_enum


class SchoolClass(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    period: Mapped[Period] = mapped_column(db_enum(Period, "class_period"))
    capacity: Mapped[int]
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # True when staff assigned the teacher; a self-claimed teacher can drop, an assigned one can't.
    teacher_locked: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    published: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Target of the enrollments (class_id, period) FK that keeps enrollments.period in sync.
        UniqueConstraint("id", "period"),
        CheckConstraint("capacity BETWEEN 1 AND 500", name="capacity_range"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("teacher_id IS NOT NULL OR NOT teacher_locked", name="locked_requires_teacher"),
        Index(
            "uq_classes_teacher_period",
            "teacher_id",
            "period",
            unique=True,
            postgresql_where=text("teacher_id IS NOT NULL"),
        ),
        Index("ix_classes_period_sort", "period", "sort_order"),
    )
