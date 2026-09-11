from typing import Any


class DomainError(Exception):
    """A business-rule failure that maps to a JSON error response.

    Rendered as {"error": {"code": ..., "message": ..., "details": ...}}.
    """

    def __init__(self, code: str, message: str, *, status_code: int = 409, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def not_found(what: str = "Resource") -> DomainError:
    return DomainError("NOT_FOUND", f"{what} not found.", status_code=404)


def forbidden(message: str = "You don't have permission to do that.", code: str = "FORBIDDEN") -> DomainError:
    return DomainError(code, message, status_code=403)


def bad_request(code: str, message: str, details: Any = None) -> DomainError:
    return DomainError(code, message, status_code=400, details=details)
