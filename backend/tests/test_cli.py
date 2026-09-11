"""The admin CLI commands documented in the README."""

from sqlalchemy import select

from app.cli import bootstrap_principal, invariants, seed
from app.db.session import get_db
from app.models import users_t
from app.models.enums import Role
from tests import factories as f


async def _role_of(email: str):
    async with get_db().sessionmaker() as session:
        return (await session.execute(select(users_t.c.role).where(users_t.c.email == email))).scalar_one()


async def test_bootstrap_principal_prepares_an_account_once(mail):
    assert await bootstrap_principal("Head@School.org", "Amina", "Rahman") == 0
    assert await _role_of("head@school.org") == Role.PRINCIPAL
    assert [e.to for e in mail.sent] == ["head@school.org"], "invite email is sent right away"
    assert await bootstrap_principal("other@school.org", "X", "Y") == 1, "refuses once a Principal exists"


async def test_bootstrap_promotes_an_existing_account():
    await f.create_user(Role.FAMILY, email="parent@school.org")
    assert await bootstrap_principal("parent@school.org", "A", "B") == 0
    assert await _role_of("parent@school.org") == Role.PRINCIPAL


async def test_seed_builds_a_consistent_demo_and_refuses_twice():
    assert await seed("Password123!") == 0
    assert await invariants() == 0
    assert await seed("Password123!") == 1
