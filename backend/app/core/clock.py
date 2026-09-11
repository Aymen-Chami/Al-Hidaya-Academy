"""Single source of "now" so tests can move time (monkeypatch `clock.utcnow`).

Always call it as `clock.utcnow()` rather than importing the function directly.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
