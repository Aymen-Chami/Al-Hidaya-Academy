from app.core.config import get_settings
from app.core.errors import DomainError
from app.models.enums import Period, Role
from app.services.engine import enrollments
from app.services.engine.tx import engine_tx
from app.services.notify.templates import TEMPLATES, render
from app.services.notify.worker import OutboxWorker
from tests import factories as f


async def test_no_email_is_queued_when_the_change_is_refused(app):
    principal = await f.create_user(Role.PRINCIPAL)
    fam, kid = await f.create_child()
    cls = await f.create_class()
    eid = await f.sign_up(fam, kid, cls)
    try:
        async with engine_tx() as tx:
            await enrollments.approve(tx, f.actor(principal), eid)
            raise DomainError("BOOM", "simulated failure after queuing an email")
    except DomainError:
        pass
    assert await f.outbox() == [], "the email row must roll back with the change"


async def test_worker_sends_and_scrubs_codes(client, mail):
    await client.post("/api/v1/auth/signup/request-code", json={"email": "new@example.com"})
    (row,) = await f.outbox("signup_code")
    code = row["params"]["code"]
    assert await OutboxWorker(mail).run_once() == 1
    (sent,) = mail.sent
    assert sent.to == "new@example.com"
    assert code in sent.subject and code in sent.body
    (row,) = await f.outbox("signup_code")
    assert row["sent_at"] is not None
    assert "code" not in row["params"], "codes aren't kept after delivery"
    assert await OutboxWorker(mail).run_once() == 0


async def test_worker_retries_with_backoff_then_gives_up(mail, frozen_clock):
    fam, kid = await f.create_child()
    principal = await f.create_user(Role.PRINCIPAL)
    eid = await f.sign_up(fam, kid, await f.create_class())
    async with engine_tx() as tx:
        await enrollments.approve(tx, f.actor(principal), eid)

    mail.fail_next = 1
    worker = OutboxWorker(mail)
    assert await worker.run_once() == 1
    (row,) = await f.outbox()
    assert row["sent_at"] is None and row["attempts"] == 1 and row["last_error"]
    assert await worker.run_once() == 0, "not due again until the backoff passes"
    frozen_clock.advance(minutes=2)
    assert await worker.run_once() == 1
    (row,) = await f.outbox()
    assert row["sent_at"] is not None
    assert [e.to for e in mail.sent] == [fam.email]

    # A permanently failing email stops being retried after the max attempts.
    eid2 = await f.sign_up(fam, kid, await f.create_class(period=Period.TWO))
    async with engine_tx() as tx:
        await enrollments.reject(tx, f.actor(principal), eid2, None)
    mail.fail_next = 1000
    for _ in range(get_settings().outbox_max_attempts + 3):
        await worker.run_once()
        frozen_clock.advance(hours=2)
    (failing,) = await f.outbox("enrollment_rejected")
    assert failing["sent_at"] is None
    assert failing["attempts"] == get_settings().outbox_max_attempts


def test_every_template_renders():
    samples = {
        "code": "123456",
        "ttl_minutes": 15,
        "first_name": "Aisha",
        "role": "teacher",
        "student_name": "Zaid Ahmed",
        "class_name": "Seerah",
        "period_label": "Period 2",
        "reason": "Not registered",
        "from_class_name": "Arabic",
        "status": "approved",
        "pruned": ["Fiqh"],
        "waitlisted": True,
    }
    for name in TEMPLATES:
        subject, body = render(name, samples)
        assert subject and body and "Al Hidayah" in body
