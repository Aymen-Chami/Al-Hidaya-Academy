"""Waitlist promotion scenarios (engine level). Invariants are asserted after every test by conftest."""

from app.models.enums import EnrollmentStatus, Period, Role
from app.services.engine import classes, enrollments, people
from app.services.engine.tx import SYSTEM, Actor, engine_tx
from tests import factories as f


async def drop(family, student_id, class_id):
    row = await f.enrollment_of(student_id, class_id)
    async with engine_tx() as tx:
        await enrollments.drop(tx, f.actor(family), row["id"], as_staff=False)


async def set_capacity(class_id, capacity):
    async with engine_tx() as tx:
        await classes.update_class(tx, SYSTEM, class_id, {"capacity": capacity})


async def full_class(capacity=1, **kw):
    """A class filled to capacity by throwaway children. Returns (class_id, [(family, kid)...])."""
    cls = await f.create_class(capacity=capacity, **kw)
    holders = []
    for _ in range(capacity):
        fam, kid = await f.create_child()
        await f.sign_up(fam, kid, cls)
        holders.append((fam, kid))
    return cls, holders


async def test_priority_beats_join_order_and_ties_go_to_earliest(app):
    cls, [(holder_fam, holder)] = await full_class()
    fam_a, a = await f.create_child()
    fam_b, b = await f.create_child()
    fam_c, c = await f.create_child()
    await f.join_waitlist(fam_a, a, cls)  # unranked, earliest
    await f.join_waitlist(fam_b, b, cls)  # unranked
    await f.join_waitlist(fam_c, c, cls, priority=2)  # ranked, latest
    assert await f.waitlisted(cls) == [c, a, b]

    await drop(holder_fam, holder, cls)
    assert await f.roster(cls) == {c}
    assert await f.status_of(c, cls) == EnrollmentStatus.PENDING

    await drop(fam_c, c, cls)
    assert await f.roster(cls) == {a}, "among unranked entries the earliest joiner goes first"


async def test_capacity_increase_promotes_as_many_as_fit(app):
    cls, _ = await full_class(capacity=2)
    waiting = []
    for _ in range(4):
        fam, kid = await f.create_child()
        await f.join_waitlist(fam, kid, cls)
        waiting.append(kid)
    await set_capacity(cls, 5)
    assert len(await f.roster(cls)) == 5
    assert await f.waitlisted(cls) == [waiting[3]]


async def test_three_level_switch_cascade(app):
    a = await f.create_class(capacity=1, name="A")
    b = await f.create_class(capacity=1, name="B")
    c = await f.create_class(capacity=1, name="C")
    fam1, s1 = await f.create_child()
    fam2, s2 = await f.create_child()
    fam3, s3 = await f.create_child()
    fam4, s4 = await f.create_child()
    await f.sign_up(fam1, s1, a)
    await f.sign_up(fam2, s2, b)
    await f.sign_up(fam3, s3, c)
    await f.join_waitlist(fam2, s2, a)  # s2 would rather be in A
    await f.join_waitlist(fam3, s3, b)  # s3 would rather be in B
    await f.join_waitlist(fam4, s4, c)  # s4 has nothing yet

    await drop(fam1, s1, a)

    assert await f.roster(a) == {s2}
    assert await f.roster(b) == {s3}
    assert await f.roster(c) == {s4}
    promoted = await f.outbox("waitlist_promoted")
    assert len(promoted) == 3
    assert {p["params"]["from_class_name"] for p in promoted} == {"B", "C", None}


async def test_mutual_waitlists_resolve_without_looping(app):
    a = await f.create_class(capacity=1, name="A")
    b = await f.create_class(capacity=1, name="B")
    fam1, s1 = await f.create_child()
    fam2, s2 = await f.create_child()
    await f.sign_up(fam1, s1, a)
    await f.sign_up(fam2, s2, b)
    await f.join_waitlist(fam1, s1, b)
    await f.join_waitlist(fam2, s2, a)

    await set_capacity(a, 2)  # s2 moves A←B, which frees B for s1, which frees a seat in A

    assert await f.roster(a) == {s2}
    assert await f.roster(b) == {s1}
    assert await f.waitlisted(a) == []
    assert await f.waitlisted(b) == []


async def test_year_class_promotion_does_not_touch_regular_periods(app):
    regular = await f.create_class()
    year, [(holder_fam, holder)] = await full_class(period=Period.YEAR)
    fam, kid = await f.create_child()
    await f.sign_up(fam, kid, regular)
    await f.join_waitlist(fam, kid, year)
    await drop(holder_fam, holder, year)
    assert kid in await f.roster(year)
    assert kid in await f.roster(regular)


async def test_rejection_frees_the_seat_for_the_waitlist(app):
    cls, [(_holder_fam, holder)] = await full_class()
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, cls)
    principal = await f.create_user(Role.PRINCIPAL)
    row = await f.enrollment_of(holder, cls)
    async with engine_tx() as tx:
        await enrollments.reject(tx, f.actor(principal), row["id"], "Payment not received")
    assert await f.roster(cls) == {kid}
    assert await f.status_of(holder, cls) == EnrollmentStatus.REJECTED


async def test_approved_status_carries_over_on_switch_but_pending_stays_pending(app):
    principal = await f.create_user(Role.PRINCIPAL)
    preferred, [(holder_fam, holder)] = await full_class()
    current = await f.create_class()
    fam, kid = await f.create_child()
    enrollment_id = await f.sign_up(fam, kid, current)
    async with engine_tx() as tx:
        await enrollments.approve(tx, f.actor(principal), enrollment_id)
    await f.join_waitlist(fam, kid, preferred)

    await drop(holder_fam, holder, preferred)
    assert await f.status_of(kid, preferred) == EnrollmentStatus.APPROVED
    assert await f.enrollment_of(kid, current) is None

    # A child switched out of a *pending* enrollment stays pending.
    preferred2, [(h2_fam, h2)] = await full_class()
    fam2, kid2 = await f.create_child()
    await f.sign_up(fam2, kid2, current)
    await f.join_waitlist(fam2, kid2, preferred2)
    await drop(h2_fam, h2, preferred2)
    assert await f.status_of(kid2, preferred2) == EnrollmentStatus.PENDING


async def test_promotion_revives_an_old_rejected_row(app):
    principal = await f.create_user(Role.PRINCIPAL)
    cls = await f.create_class(capacity=1)
    fam, kid = await f.create_child()
    rejected_id = await f.sign_up(fam, kid, cls)
    async with engine_tx() as tx:
        await enrollments.reject(tx, f.actor(principal), rejected_id, None)
    holder_fam, holder = await f.create_child()
    await f.sign_up(holder_fam, holder, cls)
    await f.join_waitlist(fam, kid, cls)

    await drop(holder_fam, holder, cls)
    row = await f.enrollment_of(kid, cls)
    assert row["id"] == rejected_id
    assert row["status"] == EnrollmentStatus.PENDING
    assert row["rejection_reason"] is None


async def test_lower_ranked_same_period_entries_are_pruned_after_promotion(app):
    first, [(h1_fam, h1)] = await full_class(name="First choice")
    second, _ = await full_class(name="Second choice")
    third, _ = await full_class(name="Unranked")
    other_period, _ = await full_class(period=Period.TWO, name="Other period")
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, first, priority=1)
    await f.join_waitlist(fam, kid, second, priority=2)
    await f.join_waitlist(fam, kid, third)
    await f.join_waitlist(fam, kid, other_period, priority=3)

    await drop(h1_fam, h1, first)

    assert kid in await f.roster(first)
    assert kid not in await f.waitlisted(second)
    assert kid not in await f.waitlisted(third)
    assert kid in await f.waitlisted(other_period), "other periods are untouched"
    (email,) = await f.outbox("waitlist_promoted")
    assert sorted(email["params"]["pruned"]) == ["Second choice", "Unranked"]


async def test_higher_ranked_entries_survive_a_promotion(app):
    top, _ = await full_class(name="Top")
    second, [(h_fam, h)] = await full_class(name="Second")
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, top, priority=1)
    await f.join_waitlist(fam, kid, second, priority=2)
    await drop(h_fam, h, second)
    assert kid in await f.roster(second)
    assert kid in await f.waitlisted(top), "they still want their 1st choice more"


async def test_unranked_promotion_prunes_nothing(app):
    a, [(h_fam, h)] = await full_class()
    b, _ = await full_class()
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, a)
    await f.join_waitlist(fam, kid, b)
    await drop(h_fam, h, a)
    assert kid in await f.roster(a)
    assert kid in await f.waitlisted(b)


async def test_drafts_and_teacherless_classes_still_promote(app):
    cls, [(h_fam, h)] = await full_class()
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, cls)
    async with engine_tx() as tx:
        await classes.update_class(tx, SYSTEM, cls, {"published": False, "teacher_id": None})
    await drop(h_fam, h, cls)
    assert await f.roster(cls) == {kid}


async def test_deleting_a_child_frees_their_seats(app):
    cls, [(h_fam, h)] = await full_class()
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, cls)
    async with engine_tx() as tx:
        await people.delete_student(tx, Actor.of(h_fam), h, as_staff=False)
    assert await f.roster(cls) == {kid}


async def test_staff_removal_emails_the_family_and_promotes(app):
    manager = await f.create_user(Role.MANAGEMENT)
    cls, [(h_fam, h)] = await full_class()
    fam, kid = await f.create_child()
    await f.join_waitlist(fam, kid, cls)
    async with await f.login(app, manager) as mc:
        row = await f.enrollment_of(h, cls)
        assert (await mc.delete(f"/api/v1/admin/enrollments/{row['id']}")).status_code == 204
    assert await f.roster(cls) == {kid}
    assert [e["to_email"] for e in await f.outbox("enrollment_removed")] == [h_fam.email]
