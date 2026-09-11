from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Role, db_enum


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(40))
    # NULL until the person completes sign-up (e.g. staff accounts created ahead of time).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        db_enum(Role, "user_role"), default=Role.FAMILY, server_default=Role.FAMILY.value
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    email_verified_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_failed_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    @property
    def is_activated(self) -> bool:
        return self.password_hash is not None


def teacher_label(first_name: str, last_name: str, display_name: str | None) -> str:
    """Public name for a teacher: their chosen display name, else "First L." like the prototype."""
    if display_name:
        return display_name
    return f"{first_name} {last_name[:1]}." if last_name else first_name
