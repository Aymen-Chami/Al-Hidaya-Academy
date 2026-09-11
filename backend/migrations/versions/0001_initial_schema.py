"""initial schema

Hand-reviewed: partial unique indexes back the business invariants (see app/services/engine/invariants.py),
and enrollments(class_id, period) -> classes(id, period) ON UPDATE CASCADE keeps enrollments.period in sync.

Revision ID: 0001
Revises:
Create Date: 2026-09-11 11:52:32.207409

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "signup",
                "password_reset",
                name="code_purpose",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("code_mac", sa.LargeBinary(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_token_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("completion_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_codes")),
        sa.UniqueConstraint(
            "completion_token_hash", name=op.f("uq_email_codes_completion_token_hash")
        ),
    )
    op.create_index(
        "ix_email_codes_lookup",
        "email_codes",
        ["email", "purpose", "created_at"],
        unique=False,
    )
    op.create_table(
        "outbox_emails",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("to_email", sa.String(length=254), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_emails")),
    )
    op.create_index(
        "ix_outbox_emails_due",
        "outbox_emails",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("sent_at IS NULL"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "family",
                "teacher",
                "management",
                "principal",
                name="user_role",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="family",
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_users_email_lowercase")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False
    )
    op.create_table(
        "classes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "period",
            sa.Enum(
                "1",
                "2",
                "3",
                "year",
                name="class_period",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "teacher_locked",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "published", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "capacity BETWEEN 1 AND 500", name=op.f("ck_classes_capacity_range")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_classes_name_length")
        ),
        sa.CheckConstraint(
            "teacher_id IS NOT NULL OR NOT teacher_locked",
            name=op.f("ck_classes_locked_requires_teacher"),
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_classes_teacher_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classes")),
        sa.UniqueConstraint("id", "period", name=op.f("uq_classes_id_period")),
    )
    op.create_index(
        "ix_classes_period_sort", "classes", ["period", "sort_order"], unique=False
    )
    op.create_index(
        "uq_classes_teacher_period",
        "classes",
        ["teacher_id", "period"],
        unique=True,
        postgresql_where=sa.text("teacher_id IS NOT NULL"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "students",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=True),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_students_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["users.id"],
            name=op.f("fk_students_family_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
    )
    op.create_index(
        op.f("ix_students_family_id"), "students", ["family_id"], unique=False
    )
    op.create_table(
        "enrollments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("class_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "period",
            sa.Enum(
                "1",
                "2",
                "3",
                "year",
                name="enrollment_period",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                name="enrollment_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "family",
                "staff",
                "waitlist",
                name="enrollment_source",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["class_id", "period"],
            ["classes.id", "classes.period"],
            name="fk_enrollments_class_period",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_enrollments_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_enrollments_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_enrollments_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint(
            "student_id", "class_id", name=op.f("uq_enrollments_student_id_class_id")
        ),
    )
    op.create_index(
        "ix_enrollments_class_status",
        "enrollments",
        ["class_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_enrollments_status_created",
        "enrollments",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_enrollments_student_period_active",
        "enrollments",
        ["student_id", "period"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'approved')"),
    )
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("class_id", sa.BigInteger(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority IS NULL OR priority BETWEEN 1 AND 3",
            name=op.f("ck_waitlist_entries_priority_range"),
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name=op.f("fk_waitlist_entries_class_id_classes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_waitlist_entries_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_waitlist_entries_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waitlist_entries")),
        sa.UniqueConstraint(
            "student_id",
            "class_id",
            name=op.f("uq_waitlist_entries_student_id_class_id"),
        ),
    )
    op.create_index(
        "ix_waitlist_entries_queue",
        "waitlist_entries",
        ["class_id", "priority", "id"],
        unique=False,
    )
    op.create_index(
        "uq_waitlist_entries_student_priority",
        "waitlist_entries",
        ["student_id", "priority"],
        unique=True,
        postgresql_where=sa.text("priority IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_waitlist_entries_student_priority",
        table_name="waitlist_entries",
        postgresql_where=sa.text("priority IS NOT NULL"),
    )
    op.drop_index("ix_waitlist_entries_queue", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
    op.drop_index(
        "uq_enrollments_student_period_active",
        table_name="enrollments",
        postgresql_where=sa.text("status IN ('pending', 'approved')"),
    )
    op.drop_index("ix_enrollments_status_created", table_name="enrollments")
    op.drop_index("ix_enrollments_class_status", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index(op.f("ix_students_family_id"), table_name="students")
    op.drop_table("students")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(
        "uq_classes_teacher_period",
        table_name="classes",
        postgresql_where=sa.text("teacher_id IS NOT NULL"),
    )
    op.drop_index("ix_classes_period_sort", table_name="classes")
    op.drop_table("classes")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_index(
        "ix_outbox_emails_due",
        table_name="outbox_emails",
        postgresql_where=sa.text("sent_at IS NULL"),
    )
    op.drop_table("outbox_emails")
    op.drop_index("ix_email_codes_lookup", table_name="email_codes")
    op.drop_table("email_codes")
