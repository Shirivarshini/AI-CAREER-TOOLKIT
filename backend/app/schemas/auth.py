"""
Auth — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the User Authentication foundation
(signup + login), following the same per-feature-module pattern as
`app/schemas/resume.py` and `app/schemas/github.py`.

How it works
------------
- `UserCreate` / `UserLogin` are the two request bodies accepted by
  `POST /auth/signup` and `POST /auth/login` respectively.
- Email format is validated with a small local regex (the same approach
  `app/schemas/github.py` uses for GitHub usernames) rather than
  Pydantic's `EmailStr`, which would pull in the `email-validator`
  package as a new dependency — not currently in `requirements.txt`.
- `UserResponse` is what a `User` ORM row is mapped to before ever being
  serialized — it deliberately excludes `hashed_password`.
- `Token` is the bearer-token envelope returned on successful login.
- `TokenData` is *not* a wire schema — it's the decoded/validated shape
  of a JWT's payload, used internally by `app/core/security.py` and any
  future "get current user" dependency.

Where future code should go
----------------------------
Future auth endpoints (e.g. refresh token, password reset, email
verification) get their own schemas here.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Deliberately simple RFC-5322-ish check: local-part@domain.tld — good enough
# to catch typos/garbage without pulling in a dedicated email-validation
# dependency. Real deliverability is out of scope for this module.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    stripped = value.strip().lower()
    if not _EMAIL_PATTERN.match(stripped):
        raise ValueError("Invalid email address format.")
    return stripped


class UserCreate(BaseModel):
    """Request body for POST /auth/signup."""

    full_name: str = Field(..., min_length=1, max_length=255, examples=["Priya Sharma"])
    email: str = Field(..., description="Must be unique.", examples=["priya@example.com"])
    password: str = Field(
        ..., min_length=8, max_length=128, description="Plain-text password (min 8 characters)."
    )

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Full name cannot be blank.")
        return stripped

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserLogin(BaseModel):
    """Request body for POST /auth/login."""

    email: str = Field(..., examples=["priya@example.com"])
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserResponse(BaseModel):
    """Public-safe representation of a User row (no password fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class Token(BaseModel):
    """
    Bearer token pair returned by POST /auth/login and POST /auth/refresh.

    A refresh token is always issued alongside the access token (and
    rotated — a new one issued, the old one blacklisted — on every
    refresh) so a client never has to re-authenticate with a password
    just because its short-lived access token expired.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime, in seconds.")


class TokenData(BaseModel):
    """Decoded/validated JWT payload — used internally, never returned over the wire."""

    user_id: uuid.UUID | None = None
    email: str | None = None
    jti: str | None = Field(None, description="Unique token id, used as the blacklist key.")
    exp: datetime | None = Field(None, description="Token expiry, used to size the blacklist TTL.")


class RefreshTokenRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """
    Request body for POST /auth/logout.

    `refresh_token` is optional: the currently-used access token (read
    from the `Authorization` header, not this body) is always
    blacklisted. Also passing the refresh token lets the client revoke
    that session's refresh token too, rather than leaving it valid until
    it naturally expires.
    """

    refresh_token: str | None = Field(None, min_length=1)
