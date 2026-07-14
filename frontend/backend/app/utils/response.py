"""
Standard API response envelope helpers.

Why this file exists
---------------------
The PRD requires: "All endpoints return standard HTTP status codes and a
consistent JSON error envelope." To keep every router's success/error
responses uniform (and predictable for the frontend), we define shared
Pydantic response wrappers here instead of returning ad-hoc dicts per
endpoint.

How it works
------------
- `SuccessResponse[T]` wraps any payload type `T` with `success: true` and
  optional `message`.
- `ErrorResponse` is the shape emitted by the global exception handler in
  `app/middlewares/error_handler.py` for any `AppException` or unhandled
  error.

Where future code should go
----------------------------
Feature routers (resume, github, linkedin, skills) should type their
`response_model` as `SuccessResponse[SomeSchema]` so Swagger UI shows the
exact envelope shape.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success envelope: {"success": true, "message": ..., "data": ...}"""

    success: bool = True
    message: str = "Request successful."
    data: T | None = None


class ErrorDetail(BaseModel):
    """A single structured error detail (used for validation errors, etc.)."""

    field: str | None = None
    issue: str


class ErrorResponse(BaseModel):
    """Standard error envelope returned by the global exception handler."""

    success: bool = False
    error_code: str
    message: str
    details: list[ErrorDetail] | None = None
