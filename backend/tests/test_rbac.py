"""Role-based access matrix for EVERY route. A new route without an entry here fails the test, so
access rules are always decided explicitly. Allowed = anything but 401/403; denied = 401 (anonymous)
or 403 (wrong role)."""

import re

import pytest

from app.models.enums import Role
from tests import factories as f

ALL = frozenset({"anon", "family", "teacher", "management", "principal"})
AUTH = ALL - {"anon"}
ADMIN = frozenset({"management", "principal"})
PRINCIPAL = frozenset({"principal"})
TEACHER = frozenset({"teacher"})
CAN_TEACH = frozenset({"teacher", "management", "principal"})

V1 = "/api/v1"
EXPECTED: dict[tuple[str, str], frozenset[str]] = {
    ("GET", "/health"): ALL,
    ("POST", "/auth/signup/request-code"): ALL,
    ("POST", "/auth/signup/verify-code"): ALL,
    ("POST", "/auth/signup/complete"): ALL,
    ("POST", "/auth/login"): ALL,
    ("POST", "/auth/logout"): ALL,
    ("POST", "/auth/password-reset/request-code"): ALL,
    ("POST", "/auth/password-reset/verify-code"): ALL,
    ("POST", "/auth/password-reset/complete"): ALL,
    ("GET", "/auth/me"): AUTH,
    ("PATCH", "/auth/me"): AUTH,
    ("POST", "/auth/me/password"): AUTH,
    ("GET", "/classes"): ALL,
    ("GET", "/classes/{class_id}"): ALL,
    ("GET", "/me/students"): AUTH,
    ("POST", "/me/students"): AUTH,
    ("PATCH", "/me/students/{student_id}"): AUTH,
    ("DELETE", "/me/students/{student_id}"): AUTH,
    ("GET", "/me/overview"): AUTH,
    ("POST", "/enrollments"): AUTH,
    ("DELETE", "/enrollments/{enrollment_id}"): AUTH,
    ("POST", "/waitlist"): AUTH,
    ("PATCH", "/waitlist/{entry_id}"): AUTH,
    ("DELETE", "/waitlist/{entry_id}"): AUTH,
    ("GET", "/teacher/classes"): CAN_TEACH,
    ("POST", "/teacher/classes/{class_id}/claim"): TEACHER,
    ("DELETE", "/teacher/classes/{class_id}/claim"): TEACHER,
    ("GET", "/admin/classes"): ADMIN,
    ("POST", "/admin/classes"): ADMIN,
    ("GET", "/admin/classes/{class_id}"): ADMIN,
    ("PATCH", "/admin/classes/{class_id}"): ADMIN,
    ("DELETE", "/admin/classes/{class_id}"): ADMIN,
    ("POST", "/admin/classes/{class_id}/move"): ADMIN,
    ("PUT", "/admin/classes/{class_id}/teacher"): ADMIN,
    ("DELETE", "/admin/classes/{class_id}/teacher"): ADMIN,
    ("POST", "/admin/classes/{class_id}/enrollments"): ADMIN,
    ("DELETE", "/admin/enrollments/{enrollment_id}"): ADMIN,
    ("DELETE", "/admin/waitlist/{entry_id}"): ADMIN,
    ("GET", "/admin/students"): ADMIN,
    ("POST", "/admin/students"): ADMIN,
    ("PATCH", "/admin/students/{student_id}"): ADMIN,
    ("DELETE", "/admin/students/{student_id}"): PRINCIPAL,
    ("GET", "/admin/users"): ADMIN,
    ("POST", "/admin/users"): PRINCIPAL,
    ("PATCH", "/admin/users/{user_id}"): PRINCIPAL,
    ("POST", "/admin/users/{user_id}/revoke-sessions"): PRINCIPAL,
    ("GET", "/admin/audit"): PRINCIPAL,
    ("GET", "/admin/enrollments"): ADMIN,
    ("POST", "/admin/enrollments/approve-bulk"): PRINCIPAL,
    ("POST", "/admin/enrollments/{enrollment_id}/approve"): PRINCIPAL,
    ("POST", "/admin/enrollments/{enrollment_id}/reject"): PRINCIPAL,
}


def api_operations(app) -> set[tuple[str, str]]:
    ops = set()
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            ops.add((method.upper(), path.removeprefix(V1)))
    return ops


def test_every_route_has_an_access_rule(app):
    assert api_operations(app) == set(EXPECTED), "update EXPECTED in tests/test_rbac.py"


@pytest.mark.parametrize("role", sorted(ALL))
async def test_access_matrix(app, role):
    user = None if role == "anon" else await f.create_user(Role(role))
    failures = []
    for (method, path), allowed in sorted(EXPECTED.items()):
        url = V1 + re.sub(r"\{[^}]+\}", "999999", path)
        # A fresh session per request, so e.g. /auth/logout can't affect the next call.
        client = await f.login(app, user) if user else f.make_client(app)
        async with client:
            kwargs = {} if method in ("GET", "DELETE") else {"json": {}}
            r = await client.request(method, url, **kwargs)
        if role in allowed:
            if r.status_code in (401, 403):
                failures.append(f"{method} {path}: expected access, got {r.status_code}")
        else:
            expected = 401 if role == "anon" else 403
            if r.status_code != expected:
                failures.append(f"{method} {path}: expected {expected}, got {r.status_code}")
    assert not failures, "\n".join(failures)
