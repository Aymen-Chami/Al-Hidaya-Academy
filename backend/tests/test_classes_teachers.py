from app.models.enums import Period, Role
from tests import factories as f

ADMIN = "/api/v1/admin/classes"


async def test_create_edit_publish_and_list(app):
    manager = await f.create_user(Role.MANAGEMENT)
    teacher = await f.create_user(Role.TEACHER, first_name="Jane", last_name="Doe")
    async with await f.login(app, manager) as mc:
        r = await mc.post(ADMIN, json={"name": "Fiqh", "period": "2", "capacity": 12, "teacher_id": teacher.id})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["teacher"]["label"] == "Jane D."
        assert body["teacher_locked"] is True
        assert body["published"] is True
        cid = body["id"]
        r = await mc.patch(f"{ADMIN}/{cid}", json={"published": False, "description": "Basics"})
        assert r.json()["published"] is False
        assert r.json()["description"] == "Basics"
    async with f.make_client(app) as anon:
        assert [c["id"] for c in (await anon.get("/api/v1/classes")).json()] == []


async def test_validation_of_class_fields(app):
    manager = await f.create_user(Role.MANAGEMENT)
    async with await f.login(app, manager) as mc:
        assert (await mc.post(ADMIN, json={"name": "", "period": "1"})).status_code == 422
        assert (await mc.post(ADMIN, json={"name": "X", "period": "4"})).status_code == 422
        assert (await mc.post(ADMIN, json={"name": "X", "period": "1", "capacity": 0})).status_code == 422
        family = await f.create_user(Role.FAMILY)
        r = await mc.post(ADMIN, json={"name": "X", "period": "1", "teacher_id": family.id})
        assert r.json()["error"]["code"] == "INVALID_TEACHER"


async def test_capacity_cannot_drop_below_seats_held(app):
    manager = await f.create_user(Role.MANAGEMENT)
    cls = await f.create_class(capacity=3)
    for _ in range(2):
        fam, kid = await f.create_child()
        await f.sign_up(fam, kid, cls)
    async with await f.login(app, manager) as mc:
        r = await mc.patch(f"{ADMIN}/{cls}", json={"capacity": 1})
        assert r.json()["error"]["code"] == "CAPACITY_BELOW_ENROLLED"
        assert (await mc.patch(f"{ADMIN}/{cls}", json={"capacity": 2})).status_code == 200


async def test_period_change_conflicts_and_cascade(app):
    manager = await f.create_user(Role.MANAGEMENT)
    teacher = await f.create_user(Role.TEACHER)
    moving = await f.create_class(period=Period.ONE, teacher=teacher)
    await f.create_class(period=Period.TWO, teacher=teacher)
    async with await f.login(app, manager) as mc:
        r = await mc.patch(f"{ADMIN}/{moving}", json={"period": "2"})
        assert r.json()["error"]["code"] == "TEACHER_PERIOD_CONFLICT"

    free_teacher_class = await f.create_class(period=Period.ONE)
    p3 = await f.create_class(period=Period.THREE)
    fam, kid = await f.create_child()
    await f.sign_up(fam, kid, free_teacher_class)
    await f.sign_up(fam, kid, p3)
    async with await f.login(app, manager) as mc:
        r = await mc.patch(f"{ADMIN}/{free_teacher_class}", json={"period": "3"})
        assert r.json()["error"]["code"] == "STUDENT_PERIOD_CONFLICT"
        assert r.json()["error"]["details"][0]["student_id"] == kid
        r = await mc.patch(f"{ADMIN}/{free_teacher_class}", json={"period": "year"})
        assert r.status_code == 200
    row = await f.enrollment_of(kid, free_teacher_class)
    assert row["period"] == Period.YEAR, "enrollment period follows its class"


async def test_teacher_assignment_locking(app):
    manager = await f.create_user(Role.MANAGEMENT)
    t1, t2 = await f.create_user(Role.TEACHER), await f.create_user(Role.TEACHER)
    cls = await f.create_class(teacher=None)
    async with await f.login(app, manager) as mc:
        r = await mc.put(f"{ADMIN}/{cls}/teacher", json={"teacher_id": t1.id})
        assert r.json()["teacher_locked"] is True
        r = await mc.patch(f"{ADMIN}/{cls}", json={"teacher_id": t1.id, "name": "Renamed"})
        assert r.json()["teacher_locked"] is True
        r = await mc.delete(f"{ADMIN}/{cls}/teacher")
        assert r.json()["teacher"] is None
        assert r.json()["teacher_locked"] is False
    async with await f.login(app, t2) as tc:
        assert (await tc.post(f"/api/v1/teacher/classes/{cls}/claim")).status_code == 204
    async with await f.login(app, manager) as mc:
        r = await mc.get(f"{ADMIN}/{cls}")
        assert r.json()["teacher"]["id"] == t2.id
        assert r.json()["teacher_locked"] is False


async def test_move_stays_within_period_and_publish_group(app):
    manager = await f.create_user(Role.MANAGEMENT)
    a = await f.create_class(name="A")
    b = await f.create_class(name="B")
    draft = await f.create_class(name="Draft", published=False)
    c = await f.create_class(name="C")
    async with await f.login(app, manager) as mc:
        assert (await mc.post(f"{ADMIN}/{c}/move", json={"direction": "up"})).status_code == 204
        assert (await mc.post(f"{ADMIN}/{a}/move", json={"direction": "up"})).status_code == 204  # already first
        assert (await mc.post(f"{ADMIN}/{draft}/move", json={"direction": "down"})).status_code == 204  # alone
    async with f.make_client(app) as anon:
        names = [x["name"] for x in (await anon.get("/api/v1/classes")).json()]
    assert names == ["A", "C", "B"]
    assert draft and b


async def test_delete_class_notifies_families(app):
    manager = await f.create_user(Role.MANAGEMENT)
    cls = await f.create_class(capacity=1)
    fam1, kid1 = await f.create_child()
    await f.sign_up(fam1, kid1, cls)
    fam2, kid2 = await f.create_child()
    await f.join_waitlist(fam2, kid2, cls)
    async with await f.login(app, manager) as mc:
        assert (await mc.delete(f"{ADMIN}/{cls}")).status_code == 204
        assert (await mc.get(f"{ADMIN}/{cls}")).status_code == 404
    emails = await f.outbox("class_cancelled")
    assert sorted(e["to_email"] for e in emails) == sorted([fam1.email, fam2.email])


async def test_teacher_claim_rules(app):
    teacher = await f.create_user(Role.TEACHER)
    other = await f.create_user(Role.TEACHER)
    p1a = await f.create_class(teacher=None)
    p1b = await f.create_class(teacher=None)
    draft = await f.create_class(teacher=None, published=False)
    async with await f.login(app, teacher) as tc:
        assert (await tc.post(f"/api/v1/teacher/classes/{draft}/claim")).status_code == 404
        assert (await tc.post(f"/api/v1/teacher/classes/{p1a}/claim")).status_code == 204
        r = await tc.post(f"/api/v1/teacher/classes/{p1b}/claim")
        assert r.json()["error"]["code"] == "TEACHER_PERIOD_CONFLICT"
    async with await f.login(app, other) as oc:
        r = await oc.post(f"/api/v1/teacher/classes/{p1a}/claim")
        assert r.json()["error"]["code"] == "ALREADY_CLAIMED"
        assert (await oc.delete(f"/api/v1/teacher/classes/{p1a}/claim")).status_code == 404
    async with await f.login(app, teacher) as tc:
        assert (await tc.delete(f"/api/v1/teacher/classes/{p1a}/claim")).status_code == 204


async def test_teacher_cannot_drop_a_staff_assigned_class(app):
    teacher = await f.create_user(Role.TEACHER)
    cls = await f.create_class(teacher=teacher)
    async with await f.login(app, teacher) as tc:
        r = await tc.delete(f"/api/v1/teacher/classes/{cls}/claim")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "CLAIM_LOCKED"


async def test_only_teachers_self_claim(app):
    cls = await f.create_class(teacher=None)
    for role in (Role.FAMILY, Role.MANAGEMENT, Role.PRINCIPAL):
        user = await f.create_user(role)
        async with await f.login(app, user) as c:
            assert (await c.post(f"/api/v1/teacher/classes/{cls}/claim")).status_code == 403


async def test_teacher_board_shows_own_classes_with_roster(app):
    teacher = await f.create_user(Role.TEACHER)
    mine = await f.create_class(teacher=teacher, capacity=1)
    draft = await f.create_class(teacher=teacher, published=False, period=Period.TWO)
    await f.create_class()  # someone else's
    fam, kid = await f.create_child()
    await f.sign_up(fam, kid, mine)
    fam2, kid2 = await f.create_child()
    await f.join_waitlist(fam2, kid2, mine)
    async with await f.login(app, teacher) as tc:
        board = (await tc.get("/api/v1/teacher/classes")).json()
    assert [c["id"] for c in board] == [mine, draft]
    assert [(r["student_id"], r["status"]) for r in board[0]["roster"]] == [(kid, "pending")]
    assert [(w["student_id"], w["position"]) for w in board[0]["waitlist"]] == [(kid2, 1)]


async def test_demoting_a_teacher_unassigns_their_classes(app):
    principal = await f.create_user(Role.PRINCIPAL)
    teacher = await f.create_user(Role.TEACHER)
    cls = await f.create_class(teacher=teacher)
    async with await f.login(app, principal) as pc:
        r = await pc.patch(f"/api/v1/admin/users/{teacher.id}", json={"role": "family"})
        assert r.json()["role"] == "family"
        assert (await pc.get(f"{ADMIN}/{cls}")).json()["teacher"] is None


async def test_deactivation_signs_the_user_out(app):
    principal = await f.create_user(Role.PRINCIPAL)
    user = await f.create_user()
    async with await f.login(app, user) as uc:
        assert (await uc.get("/api/v1/auth/me")).status_code == 200
        async with await f.login(app, principal) as pc:
            assert (await pc.patch(f"/api/v1/admin/users/{user.id}", json={"is_active": False})).status_code == 200
        assert (await uc.get("/api/v1/auth/me")).status_code == 401


async def test_last_principal_cannot_be_removed(app):
    principal = await f.create_user(Role.PRINCIPAL)
    async with await f.login(app, principal) as pc:
        r = await pc.patch(f"/api/v1/admin/users/{principal.id}", json={"role": "management"})
        assert r.json()["error"]["code"] == "LAST_PRINCIPAL"
        second = await f.create_user(Role.PRINCIPAL)
        r = await pc.patch(f"/api/v1/admin/users/{second.id}", json={"is_active": False})
        assert r.status_code == 200
        r = await pc.patch(f"/api/v1/admin/users/{principal.id}", json={"is_active": False})
        assert r.json()["error"]["code"] == "LAST_PRINCIPAL"


async def test_duplicate_email_on_user_creation(app):
    principal = await f.create_user(Role.PRINCIPAL)
    await f.create_user(email="dup@example.com")
    async with await f.login(app, principal) as pc:
        r = await pc.post(
            "/api/v1/admin/users",
            json={"email": "DUP@example.com", "first_name": "A", "last_name": "B", "role": "teacher"},
        )
        assert r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_admin_students_management(app):
    manager = await f.create_user(Role.MANAGEMENT)
    principal = await f.create_user(Role.PRINCIPAL)
    family = await f.create_user(email="parent@example.com")
    async with await f.login(app, manager) as mc:
        r = await mc.post("/api/v1/admin/students", json={"first_name": "Walk", "last_name": "In"})
        assert r.status_code == 201
        assert r.json()["family"] is None
        sid = r.json()["id"]
        r = await mc.patch(f"/api/v1/admin/students/{sid}", json={"family_id": family.id})
        assert r.json()["family"]["email"] == "parent@example.com"
        assert [s["id"] for s in (await mc.get("/api/v1/admin/students", params={"q": "walk"})).json()] == [sid]
        assert (await mc.delete(f"/api/v1/admin/students/{sid}")).status_code == 403
    async with await f.login(app, principal) as pc:
        assert (await pc.delete(f"/api/v1/admin/students/{sid}")).status_code == 204
