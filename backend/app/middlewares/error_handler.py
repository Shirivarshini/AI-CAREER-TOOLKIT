"""
Global exception handlers — translate exceptions into the standard JSON
error envelope defined in app/utils/response.py.

Why this file exists
---------------------
Per the PRD's API spec: "All endpoints return standard HTTP status codes
and a consistent JSON error envelope." Rather than wrapping every route
in try/except, FastAPI's exception-handler registration lets us catch
exceptions centrally, once, for the whole app.

How it works
------------
`register_exception_handlers(app)` is called once from `app/main.py` at
startup. It registers three handlers:
  1. `AppException` (our own hierarchy) -> mapped status code + error_code.
  2. `RequestValidationError` (Pydantic/FastAPI schema validation) -> 422
     with field-level details.
  3. `Exception` (catch-all) -> 500, logged with a full stack trace, but
     never leaks internal details to the client in production.

Where future code should go
----------------------------
If a new class of error needs special HTTP semantics, add a subclass in
app/core/exceptions.py — you should NOT need to touch this file, since
AppException subclasses are handled generically via `status_code` /
`error_code` attributes.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.core.exceptions import AppException
from app.utils.response import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app instance."""

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "AppException on %s %s -> %s: %s",
            request.method,
            request.url.path,
            exc.error_code,
            exc.message,
        )
        payload = ErrorResponse(error_code=exc.error_code, message=exc.message)
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            ErrorDetail(field=".".join(str(loc) for loc in err["loc"]), issue=err["msg"])
            for err in exc.errors()
        ]
        logger.info("Validation error on %s %s: %s", request.method, request.url.path, details)
        payload = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="One or more fields failed validation.",
            details=details,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload.model_dump()
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        settings = get_settings()
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        message = str(exc) if settings.APP_DEBUG else "An unexpected error occurred."
        payload = ErrorResponse(error_code="INTERNAL_SERVER_ERROR", message=message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload.model_dump()
        )
