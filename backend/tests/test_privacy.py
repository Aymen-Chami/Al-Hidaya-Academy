"""Children's data exposure: each audience sees only what it needs."""

from app.models.enums import Role
from tests import factories as f


def all_keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in all_keys(v)}
    return set()


async def populated_class():
    teacher = await f.create_user(Role.TEACHER, first_name="Jane", last_name="Doe")
    cls = await f.create_class(teacher=teacher, capacity=1)
    fam, kid = await f.create_child()
    await f.sign_up(fam, kid, cls)
    fam2, kid2 = await f.create_child()
    await f.join_waitlist(fam2, kid2, cls)
    return teacher, cls, fam, fam2


async def test_public_schedule_has_counts_but_no_children(app):
    _, _cls, _fam, _fam2 = await populated_class()
    async with f.make_client(app) as anon:
        r = await anon.get("/api/v1/classes")
    (item,) = r.json()
    assert set(item) == {
        "id",
        "name",
        "description",
        "period",
        "teacher",
        "capacity",
        "seats_taken",
        "seats_available",
        "is_full",
        "waitlist_count",
    }
    assert set(item["teacher"]) == {"id", "label"}
    assert item["teacher"]["label"] == "Jane D."
    assert item["seats_taken"] == 1 and item["waitlist_count"] == 1
    assert "Kid" not in r.text and "@" not in r.text


async def test_teacher_sees_names_and_status_but_no_contact_details(app):
    teacher, _, _, _ = await populated_class()
    async with await f.login(app, teacher) as tc:
        r = await tc.get("/api/v1/teacher/classes")
    keys = all_keys(r.json())
    assert {"roster", "waitlist", "first_name", "status"} <= keys
    assert not keys & {"email", "phone", "family"}
    assert "@" not in r.text


async def test_family_sees_only_their_own_children(app):
    _, cls, fam, _fam2 = await populated_class()
    async with await f.login(app, fam) as c:
        overview = (await c.get("/api/v1/me/overview")).json()
        students = (await c.get("/api/v1/me/students")).json()
    assert len(overview["students"]) == 1 == len(students)
    assert overview["students"][0]["enrollments"][0]["class_id"] == cls
    assert overview["students"][0]["waitlist"] == []


async def test_staff_views_include_family_contact_for_follow_up(app):
    _, _, fam, fam2 = await populated_class()
    manager = await f.create_user(Role.MANAGEMENT)
    async with await f.login(app, manager) as mc:
        (cls,) = (await mc.get("/api/v1/admin/classes")).json()
    assert cls["roster"][0]["family"]["email"] == fam.email
    assert cls["waitlist"][0]["family"]["email"] == fam2.email
