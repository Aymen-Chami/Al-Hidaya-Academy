from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Student(Base):
    """A child. Belongs to a family account; walk-ins created by staff may have no family."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
