import logging
from dataclasses import dataclass, field
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings

log = logging.getLogger(__name__)


class EmailBackend(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpBackend:
    async def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_username or None,
            password=s.smtp_password or None,
            start_tls=s.smtp_starttls,
            use_tls=s.smtp_use_tls,
            timeout=s.smtp_timeout_seconds,
        )


class ConsoleBackend:
    """Logs emails instead of sending them (handy for local runs without Mailpit)."""

    async def send(self, to: str, subject: str, body: str) -> None:
        log.info("EMAIL to=%s subject=%r\n%s", to, subject, body)


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


@dataclass
class MemoryBackend:
    """Collects emails in memory (tests)."""

    sent: list[SentEmail] = field(default_factory=list)
    fail_next: int = 0

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise ConnectionError("simulated SMTP failure")
        self.sent.append(SentEmail(to, subject, body))


@lru_cache
def get_backend() -> EmailBackend:
    kind = get_settings().email_backend
    if kind == "smtp":
        return SmtpBackend()
    if kind == "memory":
        return MemoryBackend()
    return ConsoleBackend()
