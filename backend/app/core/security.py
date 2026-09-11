import hashlib
import hmac
import secrets
from functools import lru_cache

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings


@lru_cache
def _hasher() -> PasswordHash:
    s = get_settings()
    return PasswordHash(
        (
            Argon2Hasher(
                time_cost=s.argon2_time_cost, memory_cost=s.argon2_memory_cost, parallelism=s.argon2_parallelism
            ),
        )
    )


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash(secrets.token_urlsafe(16))


# Argon2 is deliberately CPU-heavy, so it runs in a worker thread instead of blocking the event loop.
async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hasher().hash, password)


async def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Returns (ok, new_hash); new_hash is set when the stored hash uses outdated parameters."""
    return await run_in_threadpool(_hasher().verify_and_update, password, password_hash)


async def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so unknown emails can't be detected by timing."""
    await run_in_threadpool(_hasher().verify, password, _dummy_hash())


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def code_mac(purpose: str, email: str, code: str) -> bytes:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{purpose}:{email}:{code}".encode(), hashlib.sha256).digest()


def macs_equal(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
