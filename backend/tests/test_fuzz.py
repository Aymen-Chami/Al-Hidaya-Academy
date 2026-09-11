"""Randomized operation sequences against the engine, checking every invariant after each step.
Expected business-rule refusals (DomainError) are fine; anything else — notably a DB IntegrityError,
which would mean a pre-check missed a case — fails the test."""

import contextlib
import os
import random

import pytest
from sqlalchemy import select

from app.core.errors import DomainError
from app.db.session import get_db
from app.models import enrollments_t, students_t, waitlist_t
from app.models.enums import Period, Role
from app.services.engine import classes, enrollments, people, waitlist
from app.services.engine.invariants import check_invariants
from app.services.engine.tx import SYSTEM, engine_tx
from tests import factories as f

SEEDS = int(os.environ.get("FUZZ_SEEDS", "6"))
STEPS = int(os.environ.get("FUZZ_STEPS", "50"))


async def _ids(table, column=None):
    async with get_db().sessionmaker() as session:
        col = column if column is not None else table.c.id
        return list((await session.execute(select(col))).scalars())


async def run_fuzz(seed: int, steps: int) -> None:
    rng = random.Random(seed)
    principal = await f.create_user(Role.PRINCIPAL)
    manager = await f.create_user(Role.MANAGEMENT)
    teachers = [await f.create_user(Role.TEACHER) for _ in range(3)]
    class_ids = []
    for i, period in enumerate((Period.ONE, Period.ONE, Period.TWO, Period.TWO, Period.YEAR)):
        # Rotating teachers never gives one teacher two classes in the same period.
        teacher = teachers[i % len(teachers)] if rng.random() < 0.8 else None
        class_ids.append(await f.create_class(period=period, capacity=rng.randint(1, 2), teacher=teacher))
    families = [await f.create_family(2) for _ in range(3)]
    kids = [(fam, kid) for fam, ks in families for kid in ks]

    async def op_sign_up():
        fam, kid = rng.choice(kids)
        async with engine_tx() as tx:
            await enrollments.sign_up(tx, f.actor(fam), student_id=kid, class_id=rng.choice(class_ids))

    async def op_staff_enroll():
        _, kid = rng.choice(kids)
        async with engine_tx() as tx:
            await enrollments.staff_enroll(
                tx, f.actor(rng.choice([manager, principal])), class_id=rng.choice(class_ids), student_id=kid
            )

    async def op_join():
        fam, kid = rng.choice(kids)
        async with engine_tx() as tx:
            await waitlist.join(tx, f.actor(fam), student_id=kid, class_id=rng.choice(class_ids))

    async def op_priority():
        entries = await _ids(waitlist_t)
        if entries:
            async with engine_tx() as tx:
                await waitlist.set_priority(tx, SYSTEM, rng.choice(entries), rng.choice([1, 2, 3, None]))

    async def op_leave():
        entries = await _ids(waitlist_t)
        if entries:
            async with engine_tx() as tx:
                await waitlist.leave(tx, SYSTEM, rng.choice(entries), as_staff=True)

    async def op_drop():
        rows = await _ids(enrollments_t)
        if rows:
            async with engine_tx() as tx:
                await enrollments.drop(tx, SYSTEM, rng.choice(rows), as_staff=True)

    async def op_decide():
        rows = await _ids(enrollments_t)
        if rows:
            async with engine_tx() as tx:
                if rng.random() < 0.6:
                    await enrollments.approve(tx, f.actor(principal), rng.choice(rows))
                else:
                    await enrollments.reject(tx, f.actor(principal), rng.choice(rows), None)

    async def op_capacity():
        async with engine_tx() as tx:
            await classes.update_class(tx, SYSTEM, rng.choice(class_ids), {"capacity": rng.randint(1, 3)})

    async def op_period():
        async with engine_tx() as tx:
            await classes.update_class(tx, SYSTEM, rng.choice(class_ids), {"period": rng.choice(list(Period))})

    async def op_teacher():
        async with engine_tx() as tx:
            await classes.update_class(
                tx, SYSTEM, rng.choice(class_ids), {"teacher_id": rng.choice([t.id for t in teachers] + [None])}
            )

    async def op_delete_student():
        existing = await _ids(students_t)
        if len(existing) > 3 and rng.random() < 0.3:
            async with engine_tx() as tx:
                await people.delete_student(tx, SYSTEM, rng.choice(existing), as_staff=True)
            kids[:] = [(fam, kid) for fam, kid in kids if kid in await _ids(students_t)]

    ops = [
        (op_sign_up, 6),
        (op_staff_enroll, 2),
        (op_join, 6),
        (op_priority, 3),
        (op_leave, 1),
        (op_drop, 3),
        (op_decide, 3),
        (op_capacity, 2),
        (op_period, 1),
        (op_teacher, 1),
        (op_delete_student, 1),
    ]
    funcs, weights = zip(*ops, strict=True)
    for step in range(steps):
        op = rng.choices(funcs, weights)[0]
        with contextlib.suppress(DomainError):
            await op()
        async with get_db().sessionmaker() as session:
            violations = await check_invariants(session)
        assert not violations, f"seed={seed} step={step} op={op.__name__}: {violations}"


@pytest.mark.parametrize("seed", range(SEEDS))
async def test_random_operations_keep_invariants(seed):
    await run_fuzz(seed, STEPS)


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="set RUN_SLOW=1 for the long fuzz run")
@pytest.mark.parametrize("seed", range(100, 140))
async def test_random_operations_keep_invariants_long(seed):
    await run_fuzz(seed, 150)
