"""Migrations match the models, round-trip cleanly, and the DB constraints back up the engine."""

import asyncio

import pytest
from alembic import command
from sqlalchemy import delete, insert, make_url, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_db
from app.models import classes_t, enrollments_t, waitlist_t
from app.models.enums import EnrollmentSource, EnrollmentStatus, Period, Role
from tests import factories as f
from tests.conftest import alembic_config, recreate_database


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.json() == {"status": "ok"}


async def test_models_and_migrations_have_not_drifted(database_url):
    # alembic's env.py runs its own event loop, so run it in a worker thread.
    await asyncio.to_thread(command.check, alembic_config(database_url))


async def test_migrations_round_trip(database_url):
    scratch = make_url(database_url).set(database=make_url(database_url).database + "_roundtrip")
    url = scratch.render_as_string(hide_password=False)
    cfg = alembic_config(url)

    def round_trip():
        recreate_database(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

    await asyncio.to_thread(round_trip)
    admin = create_async_engine(scratch.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)'))
    await admin.dispose()


async def _raw(stmt):
    async with get_db().sessionmaker() as session, session.begin():
        await session.execute(stmt)


def _enrollment(student_id, class_id, period=Period.ONE, status=EnrollmentStatus.PENDING):
    return insert(enrollments_t).values(
        student_id=student_id, class_id=class_id, period=period, status=status, source=EnrollmentSource.FAMILY
    )


async def test_db_rejects_two_active_classes_in_one_period():
    _, kid = await f.create_child()
    a, b = await f.create_class(), await f.create_class()
    await _raw(_enrollment(kid, a))
    with pytest.raises(IntegrityError):
        await _raw(_enrollment(kid, b))
    # ...but a rejected one doesn't count.
    await _raw(_enrollment(kid, b, status=EnrollmentStatus.REJECTED))


async def test_db_rejects_a_second_row_for_the_same_class():
    _, kid = await f.create_child()
    a = await f.create_class()
    await _raw(_enrollment(kid, a, status=EnrollmentStatus.REJECTED))
    with pytest.raises(IntegrityError):
        await _raw(_enrollment(kid, a))


async def test_db_rejects_enrollment_period_that_differs_from_its_class():
    _, kid = await f.create_child()
    a = await f.create_class(period=Period.ONE)
    with pytest.raises(IntegrityError):
        await _raw(_enrollment(kid, a, period=Period.TWO))


async def test_db_rejects_duplicate_waitlist_rank_and_teacher_double_booking():
    _, kid = await f.create_child()
    a, b = await f.create_class(), await f.create_class()
    await _raw(insert(waitlist_t).values(student_id=kid, class_id=a, priority=1))
    with pytest.raises(IntegrityError):
        await _raw(insert(waitlist_t).values(student_id=kid, class_id=b, priority=1))

    teacher = await f.create_user(Role.TEACHER)
    await _raw(update(classes_t).where(classes_t.c.id == a).values(teacher_id=teacher.id))
    with pytest.raises(IntegrityError):
        await _raw(update(classes_t).where(classes_t.c.id == b).values(teacher_id=teacher.id))
    # These raw rows bypassed the engine (a waitlist on a class with free seats); clean up for the teardown check.
    await _raw(delete(waitlist_t))
