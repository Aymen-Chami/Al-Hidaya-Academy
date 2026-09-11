"""Every error leaves the API as {"error": {"code", "message", "details"}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DomainError

log = logging.getLogger(__name__)

HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
# lock_not_available (lock_timeout) and query_canceled (statement_timeout)
BUSY_SQLSTATES = {"55P03", "57014"}


def error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": jsonable_encoder(details)}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted input back (it may contain a password).
        details = [{"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "Some fields are missing or invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, HTTP_CODES.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        # The engine checks everything first; reaching a DB constraint means a race or a bug.
        log.error("Integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
        return error_response(409, "CONFLICT", "That change conflicts with the current data. Refresh and try again.")

    @app.exception_handler(DBAPIError)
    async def _dbapi(request: Request, exc: DBAPIError) -> JSONResponse:
        if getattr(exc.orig, "sqlstate", None) in BUSY_SQLSTATES:
            return error_response(503, "BUSY_RETRY", "The server is busy. Please try again in a moment.")
        log.exception("Database error on %s %s", request.method, request.url.path)
        return error_response(500, "INTERNAL_ERROR", "Something went wrong on our side.")
