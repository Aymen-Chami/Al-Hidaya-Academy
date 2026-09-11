"""Business invariants, checked by the tests after every engine operation and by
`python -m app.cli check-invariants`. Some are also enforced by DB constraints; I1, I4 and I5
are guaranteed only by the engine, which is why they're checked here."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHECKS: dict[str, str] = {
    "I1 active enrollments exceed capacity": """
        SELECT c.id FROM classes c JOIN enrollments e ON e.class_id = c.id AND e.status IN ('pending', 'approved')
        GROUP BY c.id, c.capacity HAVING count(*) > c.capacity""",
    "I2 more than one active enrollment per student and period": """
        SELECT student_id, period FROM enrollments WHERE status IN ('pending', 'approved')
        GROUP BY student_id, period HAVING count(*) > 1""",
    "I3 more than one enrollment row per student and class": """
        SELECT student_id, class_id FROM enrollments GROUP BY student_id, class_id HAVING count(*) > 1""",
    "I4 student both enrolled in and waitlisted on a class": """
        SELECT w.id FROM waitlist_entries w JOIN enrollments e
          ON e.student_id = w.student_id AND e.class_id = w.class_id AND e.status IN ('pending', 'approved')""",
    "I5 class with a free seat has a waitlist": """
        SELECT c.id FROM classes c
        WHERE EXISTS (SELECT 1 FROM waitlist_entries w WHERE w.class_id = c.id)
          AND c.capacity > (SELECT count(*) FROM enrollments e
                            WHERE e.class_id = c.id AND e.status IN ('pending', 'approved'))""",
    "I6 duplicate waitlist priority for a student": """
        SELECT student_id, priority FROM waitlist_entries WHERE priority IS NOT NULL
        GROUP BY student_id, priority HAVING count(*) > 1""",
    "I7 teacher has more than one class in a period": """
        SELECT teacher_id, period FROM classes WHERE teacher_id IS NOT NULL
        GROUP BY teacher_id, period HAVING count(*) > 1""",
    "I7 locked class without a teacher": "SELECT id FROM classes WHERE teacher_locked AND teacher_id IS NULL",
    "I8 enrollment period differs from its class": """
        SELECT e.id FROM enrollments e JOIN classes c ON c.id = e.class_id WHERE e.period <> c.period""",
}


async def check_invariants(session: AsyncSession) -> list[str]:
    violations = []
    for name, sql in CHECKS.items():
        rows = (await session.execute(text(sql))).all()
        if rows:
            violations.append(f"{name}: {[tuple(r) for r in rows[:5]]}")
    return violations
