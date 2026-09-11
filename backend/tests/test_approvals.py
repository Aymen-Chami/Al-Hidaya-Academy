from app.models.enums import EnrollmentStatus, Role
from tests import factories as f

Q = "/api/v1/admin/enrollments"


async def test_principal_approves_and_family_is_notified(app):
    principal = await f.create_user(Role.PRINCIPAL)
    fam, kid = await f.create_child()
    cls = await f.create_class()
    eid = await f.sign_up(fam, kid, cls)
    async with await f.login(app, principal) as pc:
        queue = (await pc.get(Q, params={"status": "pending"})).json()
        assert [e["id"] for e in queue] == [eid]
        assert queue[0]["family"]["email"] == fam.email, "contact details are there for cross-checking"
        r = await pc.post(f"{Q}/{eid}/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        assert r.json()["decided_by"]["id"] == principal.id
        assert (await pc.get(Q, params={"status": "pending"})).json() == []
    assert [e["to_email"] for e in await f.outbox("enrollment_approved")] == [fam.email]


async def test_reject_with_reason(app):
    principal = await f.create_user(Role.PRINCIPAL)
    fam, kid = await f.create_child()
    cls = await f.create_class()
    eid = await f.sign_up(fam, kid, cls)
    async with await f.login(app, principal) as pc:
        r = await pc.post(f"{Q}/{eid}/reject", json={"reason": "No registration on file"})
        assert r.json()["status"] == "rejected"
        assert r.json()["rejection_reason"] == "No registration on file"
    (email,) = await f.outbox("enrollment_rejected")
    assert email["params"]["reason"] == "No registration on file"
    async with await f.login(app, fam) as c:
        enrollment = (await c.get("/api/v1/me/overview")).json()["students"][0]["enrollments"][0]
    assert enrollment["status"] == "rejected"
    assert enrollment["rejection_reason"] == "No registration on file"


async def test_approved_enrollment_can_later_be_rejected(app):
    principal = await f.create_user(Role.PRINCIPAL)
    fam, kid = await f.create_child()
    cls = await f.create_class()
    eid = await f.sign_up(fam, kid, cls)
    async with await f.login(app, principal) as pc:
        await pc.post(f"{Q}/{eid}/approve")
        assert (await pc.post(f"{Q}/{eid}/reject", json={})).json()["status"] == "rejected"
        # Re-approving works while the seat is still free.
        assert (await pc.post(f"{Q}/{eid}/approve")).json()["status"] == "approved"


async def test_reapproving_a_rejected_request_needs_a_free_seat(app):
    principal = await f.create_user(Role.PRINCIPAL)
    cls = await f.create_class(capacity=1)
    fam, kid = await f.create_child()
    eid = await f.sign_up(fam, kid, cls)
    async with await f.login(app, principal) as pc:
        await pc.post(f"{Q}/{eid}/reject", json={})
        other_fam, other = await f.create_child()
        await f.sign_up(other_fam, other, cls)
        r = await pc.post(f"{Q}/{eid}/approve")
        assert r.json()["error"]["code"] == "CLASS_FULL"
    assert await f.status_of(kid, cls) == EnrollmentStatus.REJECTED


async def test_management_can_view_but_not_decide(app):
    manager = await f.create_user(Role.MANAGEMENT)
    fam, kid = await f.create_child()
    cls = await f.create_class()
    eid = await f.sign_up(fam, kid, cls)
    async with await f.login(app, manager) as mc:
        assert (await mc.get(Q, params={"status": "pending"})).status_code == 200
        assert (await mc.post(f"{Q}/{eid}/approve")).status_code == 403
        assert (await mc.post(f"{Q}/{eid}/reject", json={})).status_code == 403
        assert (await mc.post(f"{Q}/approve-bulk", json={"ids": [eid]})).status_code == 403


async def test_bulk_approve_reports_each_result(app):
    principal = await f.create_user(Role.PRINCIPAL)
    cls = await f.create_class(capacity=2)
    fam1, kid1 = await f.create_child()
    fam2, kid2 = await f.create_child()
    e1 = await f.sign_up(fam1, kid1, cls)
    e2 = await f.sign_up(fam2, kid2, cls)
    async with await f.login(app, principal) as pc:
        r = await pc.post(f"{Q}/approve-bulk", json={"ids": [e1, e2, 999999]})
        body = r.json()
    assert body["approved"] == [e1, e2]
    assert body["failed"] == [{"id": 999999, "code": "NOT_FOUND", "message": "Enrollment not found."}]
    assert len(await f.outbox("enrollment_approved")) == 2


async def test_queue_filters(app):
    principal = await f.create_user(Role.PRINCIPAL)
    a = await f.create_class()
    b = await f.create_class()
    fam, (k1, k2) = await f.create_family(2)
    e1 = await f.sign_up(fam, k1, a)
    await f.sign_up(fam, k2, b)
    async with await f.login(app, principal) as pc:
        assert [e["id"] for e in (await pc.get(Q, params={"class_id": a})).json()] == [e1]
        assert len((await pc.get(Q, params={"period": "1"})).json()) == 2
        assert (await pc.get(Q, params={"status": "approved"})).json() == []
