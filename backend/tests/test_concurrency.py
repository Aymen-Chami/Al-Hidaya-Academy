"""Races the engine lock must win. The first test proves the harness can actually detect
overbooking when the lock is removed, so the others aren't passing vacuously."""

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import delete, select

from app.core.errors import DomainError
from app.db.session import get_db
from app.models import enrollments_t, waitlist_t
from app.models.enums import Role
from app.services.engine import enrollments
from app.services.engine import queries as q
from app.services.engine.tx import EngineTx, engine_tx
from tests import factories as f


@asynccontextmanager
async def unlocked_tx():
    async with get_db().sessionmaker() as session, session.begin():
        yield EngineTx(session)


async def race_for_one_seat(tx_factory, monkeypatch, n=6) -> int:
    """n children try to take the single seat at once; returns how many succeeded."""
    real_seats_taken = q.seats_taken

    async def slow_seats_taken(tx, class_id):
        taken = await real_seats_taken(tx, class_id)
        await asyncio.sleep(0.05)  # widen the check-then-insert window
        return taken

    monkeypatch.setattr(q, "seats_taken", slow_seats_taken)
    cls = await f.create_class(capacity=1)
    racers = [await f.create_child() for _ in range(n)]

    async def attempt(family, kid):
        try:
            async with tx_factory() as tx:
                await enrollments.sign_up(tx, f.actor(family), student_id=kid, class_id=cls)
            return True
        except DomainError:
            return False

    results = await asyncio.gather(*(attempt(fam, kid) for fam, kid in racers))
    monkeypatch.setattr(q, "seats_taken", real_seats_taken)
    return sum(results)


async def test_without_the_lock_the_race_overbooks(monkeypatch):
    winners = await race_for_one_seat(unlocked_tx, monkeypatch)
    assert winners > 1, "harness should expose the race when the lock is removed"
    async with get_db().sessionmaker() as session, session.begin():
        await session.execute(delete(enrollments_t))  # restore invariants for the teardown check


async def test_with_the_lock_exactly_one_wins(monkeypatch):
    assert await race_for_one_seat(engine_tx, monkeypatch) == 1


async def test_last_seat_race_through_the_api(app):
    cls = await f.create_class(capacity=1)
    clients, kids = [], []
    for _ in range(20):
        fam, kid = await f.create_child()
        clients.append(await f.login(app, fam))
        kids.append(kid)
    try:
        responses = await asyncio.gather(
            *(
                c.post("/api/v1/enrollments", json={"student_id": k, "class_id": cls})
                for c, k in zip(clients, kids, strict=True)
            )
        )
    finally:
        for c in clients:
            await c.aclose()
    codes = [r.status_code for r in responses]
    assert codes.count(201) == 1, codes
    assert codes.count(409) == 19
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {"CLASS_FULL"}
    assert len(await f.roster(cls)) == 1


async def test_two_teachers_claiming_the_same_class(app):
    cls = await f.create_class(teacher=None)
    t1, t2 = await f.create_user(Role.TEACHER), await f.create_user(Role.TEACHER)
    c1, c2 = await f.login(app, t1), await f.login(app, t2)
    try:
        r1, r2 = await asyncio.gather(
            c1.post(f"/api/v1/teacher/classes/{cls}/claim"), c2.post(f"/api/v1/teacher/classes/{cls}/claim")
        )
    finally:
        await c1.aclose()
        await c2.aclose()
    assert sorted([r1.status_code, r2.status_code]) == [204, 409]


async def test_concurrent_priority_changes_keep_ranks_unique(app):
    family, kid = await f.create_child()
    entries = []
    for _ in range(3):
        cls = await f.create_class(capacity=1)
        filler_fam, filler = await f.create_child()
        await f.sign_up(filler_fam, filler, cls)
        entries.append(await f.join_waitlist(family, kid, cls))
    async with await f.login(app, family) as c:
        responses = await asyncio.gather(*(c.patch(f"/api/v1/waitlist/{e}", json={"priority": 1}) for e in entries))
    assert [r.status_code for r in responses] == [204, 204, 204]
    async with get_db().sessionmaker() as session:
        ranks = (await session.execute(select(waitlist_t.c.priority).where(waitlist_t.c.student_id == kid))).scalars()
        assert sorted(ranks, key=lambda p: p or 0) == [None, None, 1]


async def test_mixed_concurrent_operations_keep_invariants(app):
    classes = [await f.create_class(capacity=2) for _ in range(3)]
    families = [await f.create_child() for _ in range(12)]
    clients = [await f.login(app, fam) for fam, _ in families]

    async def family_session(client, kid, i):
        mine = classes[i % 3]
        other = classes[(i + 1) % 3]
        r = await client.post("/api/v1/enrollments", json={"student_id": kid, "class_id": mine})
        if r.status_code == 409:
            await client.post("/api/v1/waitlist", json={"student_id": kid, "class_id": mine})
        await client.post("/api/v1/waitlist", json={"student_id": kid, "class_id": other})
        if i % 4 == 0 and r.status_code == 201:
            await client.delete(f"/api/v1/enrollments/{r.json()['id']}")

    try:
        await asyncio.gather(
            *(family_session(c, kid, i) for i, (c, (_, kid)) in enumerate(zip(clients, families, strict=True)))
        )
    finally:
        for c in clients:
            await c.aclose()
    # conftest asserts every invariant after the test
