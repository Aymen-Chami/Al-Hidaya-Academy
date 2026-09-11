"""Helpers to build test data directly (fast) and to get logged-in API clients."""

import itertools
from typing import Any

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import get_db
from app.models import User, enrollments_t, outbox_t, waitlist_t
from app.models.enums import EnrollmentStatus, Period, Role
from app.services.auth.sessions import create_session
from app.services.engine import classes, enrollments, people, waitlist
from app.services.engine.tx import SYSTEM, Actor, engine_tx
from tests.conftest import make_client

PASSWORD = "Password123!"
_seq = itertools.count(1)


async def create_user(
    role: Role = Role.FAMILY,
    *,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str = "Tester",
    password: str | None = PASSWORD,
    is_active: bool = True,
) -> User:
    n = next(_seq)
    async with get_db().sessionmaker() as session:
        user = User(
            email=email or f"{role.value}{n}@example.com",
            first_name=first_name or f"{role.value.title()}{n}",
            last_name=last_name,
            role=role,
            password_hash=await hash_password(password) if password else None,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        return user


async def session_token(user: User) -> str:
    async with get_db().sessionmaker() as session:
        token = await create_session(session, user.id, "pytest")
        await session.commit()
        return token


async def login(app, user: User):
    """An API client carrying a fresh session cookie for `user` (caller closes it)."""
    return make_client(app, await session_token(user))


def actor(user: User) -> Actor:
    return Actor.of(user)


async def create_class(
    *,
    name: str | None = None,
    period: Period = Period.ONE,
    capacity: int = 10,
    teacher: User | bool | None = True,
    published: bool = True,
) -> int:
    """teacher=True creates a fresh teacher; pass a User to reuse one, or None/False for no teacher."""
    if teacher is True:
        teacher = await create_user(Role.TEACHER)
    teacher_id = teacher.id if isinstance(teacher, User) else None
    async with engine_tx() as tx:
        return await classes.create_class(
            tx,
            SYSTEM,
            name=name or f"Class {next(_seq)}",
            description="",
            period=period,
            capacity=capacity,
            teacher_id=teacher_id,
            published=published,
        )


async def create_family(children: int = 1) -> tuple[User, list[int]]:
    family = await create_user(Role.FAMILY)
    ids = []
    async with engine_tx() as tx:
        for _ in range(children):
            ids.append(
                await people.create_student(
                    tx, actor(family), family_id=family.id, first_name=f"Kid{next(_seq)}", last_name=f"Fam{family.id}"
                )
            )
    return family, ids


async def create_child() -> tuple[User, int]:
    family, (student_id,) = await create_family(1)
    return family, student_id


async def sign_up(family: User, student_id: int, class_id: int) -> int:
    async with engine_tx() as tx:
        return await enrollments.sign_up(tx, actor(family), student_id=student_id, class_id=class_id)


async def join_waitlist(family: User, student_id: int, class_id: int, priority: int | None = None) -> int:
    async with engine_tx() as tx:
        entry_id = await waitlist.join(tx, actor(family), student_id=student_id, class_id=class_id)
        if priority is not None:
            await waitlist.set_priority(tx, actor(family), entry_id, priority)
        return entry_id


async def enrollment_of(student_id: int, class_id: int) -> dict[str, Any] | None:
    async with get_db().sessionmaker() as session:
        row = (
            (
                await session.execute(
                    select(enrollments_t).where(
                        enrollments_t.c.student_id == student_id, enrollments_t.c.class_id == class_id
                    )
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


async def status_of(student_id: int, class_id: int) -> EnrollmentStatus | None:
    row = await enrollment_of(student_id, class_id)
    return row["status"] if row else None


async def roster(class_id: int) -> set[int]:
    """Student ids holding a seat (pending or approved)."""
    async with get_db().sessionmaker() as session:
        rows = await session.execute(
            select(enrollments_t.c.student_id).where(
                enrollments_t.c.class_id == class_id,
                enrollments_t.c.status.in_([EnrollmentStatus.PENDING, EnrollmentStatus.APPROVED]),
            )
        )
        return set(rows.scalars())


async def waitlisted(class_id: int) -> list[int]:
    """Student ids on the waitlist, in queue order."""
    async with get_db().sessionmaker() as session:
        rows = await session.execute(
            select(waitlist_t.c.student_id)
            .where(waitlist_t.c.class_id == class_id)
            .order_by(waitlist_t.c.priority.asc().nulls_last(), waitlist_t.c.id)
        )
        return list(rows.scalars())


async def outbox(template: str | None = None) -> list[dict[str, Any]]:
    async with get_db().sessionmaker() as session:
        stmt = select(outbox_t).order_by(outbox_t.c.id)
        if template:
            stmt = stmt.where(outbox_t.c.template == template)
        return [dict(r) for r in (await session.execute(stmt)).mappings()]
