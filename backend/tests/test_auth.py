import asyncio

from app.core.config import get_settings
from app.models.enums import Role
from tests import factories as f

SIGNUP = "/api/v1/auth/signup"
RESET = "/api/v1/auth/password-reset"


async def latest_code(email: str, template: str = "signup_code") -> str:
    rows = [r for r in await f.outbox(template) if r["to_email"] == email]
    assert rows, f"no {template} email for {email}"
    return rows[-1]["params"]["code"]


async def signup(client, email: str, password: str = "NewPassw0rd!") -> dict:
    assert (await client.post(f"{SIGNUP}/request-code", json={"email": email})).status_code == 202
    code = await latest_code(email.strip().lower())
    r = await client.post(f"{SIGNUP}/verify-code", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    token = r.json()["completion_token"]
    r = await client.post(
        f"{SIGNUP}/complete",
        json={"completion_token": token, "first_name": "Maryam", "last_name": "Yusuf", "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_full_signup_login_logout(client):
    me = await signup(client, "  Parent@Example.com ")
    assert me["email"] == "parent@example.com"
    assert me["role"] == "family"
    cookie = client.cookies.get(get_settings().session_cookie_name)
    assert cookie

    assert (await client.get("/api/v1/auth/me")).json()["email"] == "parent@example.com"
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    r = await client.post("/api/v1/auth/login", json={"email": "PARENT@example.com", "password": "NewPassw0rd!"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_session_cookie_flags(client):
    await f.create_user(email="flags@example.com")
    r = await client.post("/api/v1/auth/login", json={"email": "flags@example.com", "password": f.PASSWORD})
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie


async def test_request_code_for_existing_account_sends_notice_not_code(client):
    await f.create_user(email="taken@example.com")
    r = await client.post(f"{SIGNUP}/request-code", json={"email": "taken@example.com"})
    assert r.status_code == 202
    assert await f.outbox("signup_code") == []
    assert [e["to_email"] for e in await f.outbox("account_exists")] == ["taken@example.com"]
    # Nothing verifiable was created.
    r = await client.post(f"{SIGNUP}/verify-code", json={"email": "taken@example.com", "code": "123456"})
    assert r.json()["error"]["code"] == "INVALID_CODE"


async def test_wrong_code_attempts_are_limited(client):
    await client.post(f"{SIGNUP}/request-code", json={"email": "guess@example.com"})
    code = await latest_code("guess@example.com")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(get_settings().code_max_attempts):
        r = await client.post(f"{SIGNUP}/verify-code", json={"email": "guess@example.com", "code": wrong})
        assert r.status_code == 400
    r = await client.post(f"{SIGNUP}/verify-code", json={"email": "guess@example.com", "code": code})
    assert r.status_code == 400, "the correct code must stop working after too many attempts"


async def test_code_expires(client, frozen_clock):
    await client.post(f"{SIGNUP}/request-code", json={"email": "late@example.com"})
    code = await latest_code("late@example.com")
    frozen_clock.advance(minutes=get_settings().code_ttl_minutes + 1)
    r = await client.post(f"{SIGNUP}/verify-code", json={"email": "late@example.com", "code": code})
    assert r.json()["error"]["code"] == "INVALID_CODE"


async def test_code_request_cooldown_and_hourly_cap(client, frozen_clock):
    body = {"email": "spam@example.com"}
    assert (await client.post(f"{SIGNUP}/request-code", json=body)).status_code == 202
    r = await client.post(f"{SIGNUP}/request-code", json=body)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    for _ in range(get_settings().code_max_per_hour - 1):
        frozen_clock.advance(seconds=61)
        assert (await client.post(f"{SIGNUP}/request-code", json=body)).status_code == 202
    frozen_clock.advance(seconds=61)
    assert (await client.post(f"{SIGNUP}/request-code", json=body)).status_code == 429
    # A newer code replaces the older ones.
    codes = [e["params"]["code"] for e in await f.outbox("signup_code")]
    r = await client.post(f"{SIGNUP}/verify-code", json={"email": "spam@example.com", "code": codes[-1]})
    assert r.status_code == 200


async def test_staff_created_account_keeps_role_on_signup(app, client):
    principal = await f.create_user(Role.PRINCIPAL)
    async with await f.login(app, principal) as pc:
        r = await pc.post(
            "/api/v1/admin/users",
            json={"email": "newteacher@example.com", "first_name": "Aisha", "last_name": "Khan", "role": "teacher"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["activated"] is False
    assert [e["to_email"] for e in await f.outbox("account_invite")] == ["newteacher@example.com"]
    me = await signup(client, "newteacher@example.com")
    assert me["role"] == "teacher"


async def test_completion_token_is_single_use_even_concurrently(client):
    await client.post(f"{SIGNUP}/request-code", json={"email": "once@example.com"})
    code = await latest_code("once@example.com")
    token = (await client.post(f"{SIGNUP}/verify-code", json={"email": "once@example.com", "code": code})).json()[
        "completion_token"
    ]
    body = {"completion_token": token, "first_name": "A", "last_name": "B", "password": "Passw0rd!!"}
    results = await asyncio.gather(*(client.post(f"{SIGNUP}/complete", json=body) for _ in range(3)))
    assert sorted(r.status_code for r in results) == [201, 400, 400]


async def test_login_errors_do_not_reveal_accounts(client):
    await f.create_user(email="real@example.com")
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
    wrong = await client.post("/api/v1/auth/login", json={"email": "real@example.com", "password": "x"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_login_blocked_for_inactive_and_unactivated(client):
    await f.create_user(email="off@example.com", is_active=False)
    await f.create_user(email="pending@example.com", password=None)
    r = await client.post("/api/v1/auth/login", json={"email": "off@example.com", "password": f.PASSWORD})
    assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    r = await client.post("/api/v1/auth/login", json={"email": "pending@example.com", "password": f.PASSWORD})
    assert r.status_code == 401


async def test_repeated_login_failures_back_off(client, frozen_clock):
    await f.create_user(email="brute@example.com")
    for _ in range(get_settings().login_failures_before_backoff):
        await client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": "wrong"})
    r = await client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": f.PASSWORD})
    assert r.status_code == 429
    frozen_clock.advance(seconds=get_settings().login_backoff_base_seconds + 1)
    r = await client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": f.PASSWORD})
    assert r.status_code == 200


async def test_password_reset_revokes_old_sessions(app, client):
    user = await f.create_user(email="forgot@example.com")
    old = await f.login(app, user)
    assert (await old.get("/api/v1/auth/me")).status_code == 200

    assert (await client.post(f"{RESET}/request-code", json={"email": "forgot@example.com"})).status_code == 202
    code = await latest_code("forgot@example.com", "reset_code")
    token = (await client.post(f"{RESET}/verify-code", json={"email": "forgot@example.com", "code": code})).json()[
        "completion_token"
    ]
    r = await client.post(f"{RESET}/complete", json={"completion_token": token, "new_password": "BrandNew123"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await old.get("/api/v1/auth/me")).status_code == 401
    await old.aclose()
    r = await client.post("/api/v1/auth/login", json={"email": "forgot@example.com", "password": "BrandNew123"})
    assert r.status_code == 200


async def test_reset_for_unknown_email_is_silent(client):
    r = await client.post(f"{RESET}/request-code", json={"email": "ghost@example.com"})
    assert r.status_code == 202
    assert await f.outbox() == []


async def test_change_password_keeps_current_session_only(app):
    user = await f.create_user()
    current, other = await f.login(app, user), await f.login(app, user)
    r = await current.post("/api/v1/auth/me/password", json={"current_password": "nope", "new_password": "Another123"})
    assert r.status_code == 400
    r = await current.post(
        "/api/v1/auth/me/password", json={"current_password": f.PASSWORD, "new_password": "Another123"}
    )
    assert r.status_code == 204
    assert (await current.get("/api/v1/auth/me")).status_code == 200
    assert (await other.get("/api/v1/auth/me")).status_code == 401
    await current.aclose()
    await other.aclose()


async def test_update_profile(app):
    user = await f.create_user()
    async with await f.login(app, user) as c:
        r = await c.patch("/api/v1/auth/me", json={"phone": "555-0100", "display_name": "Sr. Amina"})
        assert r.json()["phone"] == "555-0100"
        assert r.json()["display_name"] == "Sr. Amina"
        r = await c.patch("/api/v1/auth/me", json={"display_name": ""})
        assert r.json()["display_name"] is None


async def test_cross_site_origin_is_blocked(client):
    r = await client.post("/api/v1/auth/logout", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "BAD_ORIGIN"
    allowed = await client.post("/api/v1/auth/logout", headers={"origin": "http://localhost:5173"})
    assert allowed.status_code == 204


async def test_validation_errors_never_echo_passwords(client):
    r = await client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "SuperSecret!"})
    assert r.status_code == 422
    assert "SuperSecret" not in r.text
