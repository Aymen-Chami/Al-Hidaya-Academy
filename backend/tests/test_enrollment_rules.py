"""Sign-up and waitlist rules through the API (the prototype's rules, enforced server-side)."""

from app.models.enums import EnrollmentStatus, Period, Role
from tests import factories as f


async def post_enroll(c, student_id, class_id):
    return await c.post("/api/v1/enrollments", json={"student_id": student_id, "class_id": class_id})


async def post_waitlist(c, student_id, class_id):
    return await c.post("/api/v1/waitlist", json={"student_id": student_id, "class_id": class_id})


async def test_signup_starts_pending_and_holds_a_seat(app):
    family, kid = await f.create_child()
    cls = await f.create_class(capacity=2)
    async with await f.login(app, family) as c:
        r = await post_enroll(c, kid, cls)
        assert r.status_code == 201
        assert r.json()["status"] == "pending"
        info = (await c.get(f"/api/v1/classes/{cls}")).json()
    assert info["seats_taken"] == 1
    assert info["seats_available"] == 1


async def test_one_class_per_period_but_year_bucket_is_independent(app):
    family, kid = await f.create_child()
    p1a, p1b = await f.create_class(), await f.create_class()
    year = await f.create_class(period=Period.YEAR)
    p2 = await f.create_class(period=Period.TWO)
    async with await f.login(app, family) as c:
        assert (await post_enroll(c, kid, p1a)).status_code == 201
        r = await post_enroll(c, kid, p1b)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "PERIOD_CONFLICT"
        assert (await post_enroll(c, kid, year)).status_code == 201
        assert (await post_enroll(c, kid, p2)).status_code == 201
        assert (await post_enroll(c, kid, p1a)).json()["error"]["code"] == "ALREADY_ENROLLED"


async def test_capacity_is_enforced(app):
    cls = await f.create_class(capacity=1)
    fam1, kid1 = await f.create_child()
    fam2, kid2 = await f.create_child()
    await f.sign_up(fam1, kid1, cls)
    async with await f.login(app, fam2) as c:
        r = await post_enroll(c, kid2, cls)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CLASS_FULL"


async def test_drafts_are_hidden_and_teacherless_classes_are_closed(app):
    family, kid = await f.create_child()
    draft = await f.create_class(published=False)
    no_teacher = await f.create_class(teacher=None)
    async with await f.login(app, family) as c:
        assert (await post_enroll(c, kid, draft)).status_code == 404
        assert (await c.get(f"/api/v1/classes/{draft}")).status_code == 404
        r = await post_enroll(c, kid, no_teacher)
        assert r.json()["error"]["code"] == "CLASS_NOT_OPEN"


async def test_cannot_act_on_another_familys_child(app):
    _, their_kid = await f.create_child()
    me, _ = await f.create_child()
    cls = await f.create_class()
    async with await f.login(app, me) as c:
        assert (await post_enroll(c, their_kid, cls)).status_code == 404
        assert (await c.delete(f"/api/v1/me/students/{their_kid}")).status_code == 404
        assert (await c.patch(f"/api/v1/me/students/{their_kid}", json={"first_name": "X"})).status_code == 404


async def test_family_can_reapply_after_rejection_reusing_the_row(app):
    family, kid = await f.create_child()
    cls = await f.create_class()
    enrollment_id = await f.sign_up(family, kid, cls)
    principal = await f.create_user(Role.PRINCIPAL)
    async with await f.login(app, principal) as pc:
        assert (await pc.post(f"/api/v1/admin/enrollments/{enrollment_id}/reject", json={})).status_code == 200
    async with await f.login(app, family) as c:
        overview = (await c.get("/api/v1/me/overview")).json()
        assert overview["students"][0]["enrollments"][0]["status"] == "rejected"
        r = await post_enroll(c, kid, cls)
        assert r.status_code == 201
        assert r.json()["id"] == enrollment_id
    assert await f.status_of(kid, cls) == EnrollmentStatus.PENDING


async def test_rejected_enrollment_does_not_block_the_period(app):
    family, kid = await f.create_child()
    a, b = await f.create_class(), await f.create_class()
    enrollment_id = await f.sign_up(family, kid, a)
    principal = await f.create_user(Role.PRINCIPAL)
    async with await f.login(app, principal) as pc:
        await pc.post(f"/api/v1/admin/enrollments/{enrollment_id}/reject", json={"reason": "Not registered"})
    async with await f.login(app, family) as c:
        assert (await post_enroll(c, kid, b)).status_code == 201
        # Dismissing the rejected request removes it.
        assert (await c.delete(f"/api/v1/enrollments/{enrollment_id}")).status_code == 204
    assert await f.enrollment_of(kid, a) is None


async def test_staff_add_is_pending_for_management_and_approved_for_principal(app):
    manager = await f.create_user(Role.MANAGEMENT)
    principal = await f.create_user(Role.PRINCIPAL)
    _, kid1 = await f.create_child()
    family2, kid2 = await f.create_child()
    draft = await f.create_class(published=False, teacher=None)
    async with await f.login(app, manager) as mc:
        r = await mc.post(f"/api/v1/admin/classes/{draft}/enrollments", json={"student_id": kid1})
        assert r.status_code == 201
        assert r.json()["status"] == "pending"
    async with await f.login(app, principal) as pc:
        r = await pc.post(f"/api/v1/admin/classes/{draft}/enrollments", json={"student_id": kid2})
        assert r.json()["status"] == "approved"
    assert await f.status_of(kid1, draft) == EnrollmentStatus.PENDING
    assert await f.status_of(kid2, draft) == EnrollmentStatus.APPROVED
    assert [e["to_email"] for e in await f.outbox("enrollment_approved")] == [family2.email]


async def test_staff_add_respects_capacity_and_periods(app):
    manager = await f.create_user(Role.MANAGEMENT)
    family, kid = await f.create_child()
    _, other = await f.create_child()
    full = await f.create_class(capacity=1)
    await f.sign_up(family, kid, full)
    elsewhere = await f.create_class()
    async with await f.login(app, manager) as mc:
        r = await mc.post(f"/api/v1/admin/classes/{full}/enrollments", json={"student_id": other})
        assert r.json()["error"]["code"] == "CLASS_FULL"
        r = await mc.post(f"/api/v1/admin/classes/{elsewhere}/enrollments", json={"student_id": kid})
        assert r.json()["error"]["code"] == "PERIOD_CONFLICT"


async def test_waitlist_join_rules(app):
    family, kid = await f.create_child()
    cls = await f.create_class(capacity=1)
    async with await f.login(app, family) as c:
        r = await post_waitlist(c, kid, cls)
        assert r.json()["error"]["code"] == "HAS_OPEN_SEATS"
        await post_enroll(c, kid, cls)
        r = await post_waitlist(c, kid, cls)
        assert r.json()["error"]["code"] == "ALREADY_ENROLLED"

    other_family, other_kid = await f.create_child()
    elsewhere = await f.create_class()
    await f.sign_up(other_family, other_kid, elsewhere)
    async with await f.login(app, other_family) as c:
        # Holding a class in the same period doesn't prevent waiting for another one.
        assert (await post_waitlist(c, other_kid, cls)).status_code == 201
        assert (await post_waitlist(c, other_kid, cls)).json()["error"]["code"] == "ALREADY_WAITLISTED"


async def test_priorities_are_unique_per_child_and_positions_follow_priority(app):
    cls_a = await f.create_class(capacity=1)
    cls_b = await f.create_class(capacity=1)
    filler_fam, (f1, f2) = await f.create_family(2)
    await f.sign_up(filler_fam, f1, cls_a)
    await f.sign_up(filler_fam, f2, cls_b)
    early_fam, early = await f.create_child()
    await f.join_waitlist(early_fam, early, cls_a)
    family, kid = await f.create_child()
    entry_a = await f.join_waitlist(family, kid, cls_a)
    entry_b = await f.join_waitlist(family, kid, cls_b)

    async with await f.login(app, family) as c:
        assert (await c.patch(f"/api/v1/waitlist/{entry_a}", json={"priority": 1})).status_code == 204
        assert (await c.patch(f"/api/v1/waitlist/{entry_b}", json={"priority": 1})).status_code == 204
        waitlist = {w["class_id"]: w for w in (await c.get("/api/v1/me/overview")).json()["students"][0]["waitlist"]}
    assert waitlist[cls_b]["priority"] == 1
    assert waitlist[cls_a]["priority"] is None, "claiming rank 1 elsewhere clears it here"
    assert waitlist[cls_a]["position"] == 2 and waitlist[cls_a]["size"] == 2

    async with await f.login(app, family) as c:
        await c.patch(f"/api/v1/waitlist/{entry_a}", json={"priority": 2})
        waitlist = {w["class_id"]: w for w in (await c.get("/api/v1/me/overview")).json()["students"][0]["waitlist"]}
    assert waitlist[cls_a]["position"] == 1, "a ranked entry goes ahead of earlier unranked ones"


async def test_leave_waitlist(app):
    cls = await f.create_class(capacity=1)
    fam1, kid1 = await f.create_child()
    await f.sign_up(fam1, kid1, cls)
    family, kid = await f.create_child()
    entry = await f.join_waitlist(family, kid, cls)
    async with await f.login(app, family) as c:
        assert (await c.delete(f"/api/v1/waitlist/{entry}")).status_code == 204
    assert await f.waitlisted(cls) == []
