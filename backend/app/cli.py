"""Admin commands:  python -m app.cli <command> ...

bootstrap-principal --email E --first-name F --last-name L
    Prepare the first Principal account (refuses if an active Principal exists). They then
    sign up with that email to set a password.
seed [--password P]
    Load demo users, children and classes (development only).
check-invariants
    Verify the enrollment invariants; exits 1 if any are violated.
send-test-email --to E
    Send one email through the configured backend, to check SMTP settings.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User, users_t
from app.models.enums import Period, Role
from app.services.engine import classes, enrollments, people, waitlist
from app.services.engine.invariants import check_invariants
from app.services.engine.tx import SYSTEM, Actor, engine_tx
from app.services.notify.backends import get_backend
from app.services.notify.worker import OutboxWorker


async def bootstrap_principal(email: str, first_name: str, last_name: str) -> int:
    email = email.strip().lower()
    async with engine_tx() as tx:
        principals = (
            await tx.session.execute(
                select(func.count()).where(users_t.c.role == Role.PRINCIPAL, users_t.c.is_active.is_(True))
            )
        ).scalar_one()
        if principals:
            print("An active Principal already exists — manage accounts from the Principal's dashboard instead.")
            return 1
        existing = (await tx.session.execute(select(users_t.c.id).where(users_t.c.email == email))).first()
        if existing:
            await people.update_user(tx, SYSTEM, existing.id, {"role": Role.PRINCIPAL, "is_active": True})
        else:
            await people.create_user(
                tx,
                SYSTEM,
                email=email,
                first_name=first_name,
                last_name=last_name,
                display_name=None,
                phone=None,
                role=Role.PRINCIPAL,
                send_invite=True,
            )
    await OutboxWorker().run_once()
    print(f"Principal account ready for {email}.")
    print(f"If it isn't activated yet, sign up at {get_settings().app_base_url} with that email to choose a password.")
    return 0


async def seed(password: str) -> int:
    if get_settings().env == "production":
        print("Refusing to seed demo data in production.")
        return 1
    async with get_db().sessionmaker() as session:
        if (await session.execute(select(func.count()).select_from(users_t))).scalar_one():
            print("Database already has users; seed skipped.")
            return 1
        pw = await hash_password(password)

        def user(email: str, first: str, last: str, role: Role) -> User:
            return User(email=email, first_name=first, last_name=last, role=role, password_hash=pw)

        staff = {
            "principal": user("principal@example.com", "Amina", "Rahman", Role.PRINCIPAL),
            "manager": user("manager@example.com", "Omar", "Siddiqui", Role.MANAGEMENT),
            "t1": user("teacher1@example.com", "Aisha", "Khan", Role.TEACHER),
            "t2": user("teacher2@example.com", "Yusuf", "Ali", Role.TEACHER),
            "t3": user("teacher3@example.com", "Maryam", "Hussain", Role.TEACHER),
        }
        families = [
            user("family1@example.com", "Fatima", "Ahmed", Role.FAMILY),
            user("family2@example.com", "Ibrahim", "Malik", Role.FAMILY),
            user("family3@example.com", "Khadija", "Noor", Role.FAMILY),
        ]
        session.add_all([*staff.values(), *families])
        await session.commit()

    manager = Actor(id=staff["manager"].id, role=Role.MANAGEMENT)
    principal = Actor(id=staff["principal"].id, role=Role.PRINCIPAL)
    async with engine_tx() as tx:
        spec = [
            ("Qur'an Recitation", "Tajweed basics and memorisation.", Period.ONE, 3, staff["t1"].id),
            ("Arabic Letters", "Reading and writing the alphabet.", Period.ONE, 8, staff["t2"].id),
            ("Seerah Stories", "The life of the Prophet ﷺ.", Period.TWO, 10, staff["t3"].id),
            ("Islamic Manners", "Adab at home and at school.", Period.TWO, 10, None),
            ("Duas for Every Day", "Short supplications.", Period.THREE, 12, staff["t1"].id),
            ("Hifz Circle", "Year-long memorisation circle.", Period.YEAR, 6, staff["t2"].id),
        ]
        class_ids = []
        for name, desc, period, capacity, teacher_id in spec:
            class_ids.append(
                await classes.create_class(
                    tx,
                    manager,
                    name=name,
                    description=desc,
                    period=period,
                    capacity=capacity,
                    teacher_id=teacher_id,
                    published=True,
                )
            )
        children = []
        for fam, kids in zip(families, (["Zaid", "Hana"], ["Bilal"], ["Sara", "Adam"]), strict=True):
            fam_actor = Actor(id=fam.id, role=Role.FAMILY)
            for first in kids:
                sid = await people.create_student(
                    tx, fam_actor, family_id=fam.id, first_name=first, last_name=fam.last_name
                )
                children.append((fam_actor, sid))
        # Fill "Qur'an Recitation" (3 seats), then waitlist two more children.
        for fam_actor, sid in children[:3]:
            await enrollments.sign_up(tx, fam_actor, student_id=sid, class_id=class_ids[0])
        for fam_actor, sid in children[3:5]:
            await enrollments.sign_up(tx, fam_actor, student_id=sid, class_id=class_ids[1])
            await waitlist.join(tx, fam_actor, student_id=sid, class_id=class_ids[0])
        first_enrollment = await enrollments.sign_up(
            tx, children[0][0], student_id=children[0][1], class_id=class_ids[2]
        )
        await enrollments.approve(tx, principal, first_enrollment)

    print("Seeded demo data. Every account's password is:", password)
    for label, u in [*staff.items(), *((f"family{i + 1}", f) for i, f in enumerate(families))]:
        print(f"  {label:10} {u.email:26} {u.role}")
    return 0


async def invariants() -> int:
    async with get_db().sessionmaker() as session:
        violations = await check_invariants(session)
    if violations:
        print("Invariant violations:\n  " + "\n  ".join(violations))
        return 1
    print("All enrollment invariants hold.")
    return 0


async def send_test_email(to: str) -> int:
    s = get_settings()
    print(
        f"backend={s.email_backend} host={s.smtp_host}:{s.smtp_port} "
        f"starttls={s.smtp_starttls} tls={s.smtp_use_tls} user={s.smtp_username or '(none)'}"
    )
    try:
        await get_backend().send(
            to.strip(),
            "Al Hidayah Academy — SMTP test",
            "This is a test message. If you are reading it, outgoing email works.",
        )
    except Exception as exc:  # report whatever the relay said, however it failed
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"Sent to {to}. Check the inbox (and the spam folder).")
    return 0


async def _run(coro) -> int:
    try:
        return await coro
    finally:
        await get_db().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    bp = sub.add_parser("bootstrap-principal", help="prepare the first Principal account")
    bp.add_argument("--email", required=True)
    bp.add_argument("--first-name", required=True)
    bp.add_argument("--last-name", required=True)
    sp = sub.add_parser("seed", help="load demo data (development only)")
    sp.add_argument("--password", default="Password123!")
    sub.add_parser("check-invariants", help="verify enrollment invariants")
    te = sub.add_parser("send-test-email", help="send one email to check SMTP settings")
    te.add_argument("--to", required=True)
    args = parser.parse_args(argv)

    if args.command == "bootstrap-principal":
        coro = bootstrap_principal(args.email, args.first_name, args.last_name)
    elif args.command == "seed":
        coro = seed(args.password)
    elif args.command == "send-test-email":
        coro = send_test_email(args.to)
    else:
        coro = invariants()
    return asyncio.run(_run(coro))


if __name__ == "__main__":
    sys.exit(main())
