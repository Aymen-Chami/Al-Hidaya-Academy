from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, LargeBinary, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import CodePurpose, db_enum


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the cookie value; the raw token is never stored.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    last_used_at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(String(255))


class EmailCode(Base):
    """One-time email code for sign-up or password reset.

    After a correct code, a single-use completion token (hashed here) authorizes the final step.
    """

    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    purpose: Mapped[CodePurpose] = mapped_column(db_enum(CodePurpose, "code_purpose"))
    code_mac: Mapped[bytes] = mapped_column(LargeBinary(32))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    verified_at: Mapped[datetime | None]
    completion_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), unique=True)
    completion_expires_at: Mapped[datetime | None]
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (Index("ix_email_codes_lookup", "email", "purpose", "created_at"),)
