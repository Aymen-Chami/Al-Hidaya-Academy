import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.api.errors import install_error_handlers
from app.api.routes import admin_classes, admin_people, approvals, auth, classes, family, health, teacher
from app.core.config import get_settings
from app.core.csrf import OriginCheckMiddleware
from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.services.notify.worker import OutboxWorker

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker_task = None
    if get_settings().outbox_worker_enabled:
        worker_task = asyncio.create_task(OutboxWorker().run_forever(), name="outbox-worker")
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
        await get_db().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    docs = settings.docs_enabled
    app = FastAPI(
        title="Al Hidayah Academy — Sunday School Sign-up API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.add_middleware(OriginCheckMiddleware)
    install_error_handlers(app)

    # Document the real error shape ({"error": {code, message, details}}) for API consumers.
    error = {"model": ErrorResponse}
    api = APIRouter(
        prefix=API_PREFIX,
        responses={400: error, 401: error, 403: error, 404: error, 409: error, 422: error, 429: error},
    )
    for module in (health, auth, classes, family, teacher, admin_classes, admin_people, approvals):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
