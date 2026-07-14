"""
Password hashing & JWT utilities.

Why this file exists
---------------------
Two cross-cutting security concerns that any auth-adjacent module needs:
(1) hashing/verifying passwords, and (2) issuing/decoding JWT access and
refresh tokens. Centralizing them here — rather than inline in
`AuthService` — means the authorization dependencies in `app/api/deps.py`
can decode a token without importing the Auth service layer, and any
future module (email verification, password reset) can reuse the same
token machinery.

How it works
------------
- Password hashing uses `passlib`'s `CryptContext` configured for
  bcrypt. `deprecated="auto"` means if a stronger scheme is added later,
  existing bcrypt hashes still verify correctly and are only flagged for
  (optional) rehashing.
- Every issued token — access or refresh — carries:
    - `sub`  — the user id (JWT convention for "subject").
    - `email` — convenience claim, avoids a DB round-trip for display.
    - `type` — `"access"` or `"refresh"`, so a refresh token can never be
      replayed where an access token is expected, and vice versa.
    - `jti`  — a per-token random id, used as the blacklist key on
      logout/rotation (see `app/repositories/token_blacklist_repository.py`).
    - `iat` / `exp` — issued-at / expiry, standard JWT claims.
  This shared shape is what makes future token types (e.g. a
  `"password_reset"` or `"email_verification"` token) a matter of adding
  a new `expected_type` value to `decode_token()`, not new machinery.
- `decode_token()` is the single place that verifies a JWT's signature
  and claims. It distinguishes an **expired** signature (`TokenExpiredError`,
  still a well-formed token — a client can silently refresh) from an
  **invalid** one (`InvalidTokenError` — bad signature, wrong `type`,
  missing claims — the client must log in again). Both are subclasses of
  `UnauthorizedError`, so unhandled callers still get a 401, but a
  frontend that wants to special-case "refresh silently" vs. "redirect
  to login" can branch on `error_code`.

Where future code should go
----------------------------
Password-reset / email-verification tokens: add `expected_type="password_reset"`
/ `"email_verification"` calls to `create_token()` / `decode_token()`
below — no new JWT plumbing needed, just new service methods and
endpoints that use these two functions with a different `type` claim and
a short expiry.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import Settings, get_settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    user_id: uuid.UUID,
    email: str,
    token_type: TokenType,
    expire_delta: timedelta,
    settings: Settings,
) -> tuple[str, int]:
    """Shared encoder for access/refresh tokens — see module docstring for claim shape."""
    now = datetime.now(timezone.utc)
    expire_at = now + expire_delta

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire_at,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, int(expire_delta.total_seconds())


def create_access_token(
    user_id: uuid.UUID,
    email: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Build and sign a short-lived JWT access token. Returns `(token, expires_in_seconds)`."""
    settings = settings or get_settings()
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(user_id, email, "access", delta, settings)


def create_refresh_token(
    user_id: uuid.UUID,
    email: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Build and sign a long-lived JWT refresh token. Returns `(token, expires_in_seconds)`."""
    settings = settings or get_settings()
    delta = expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(user_id, email, "refresh", delta, settings)


def decode_token(
    token: str,
    expected_type: TokenType,
    settings: Settings | None = None,
) -> TokenData:
    """
    Verify and decode a JWT into a `TokenData`, enforcing that its `type`
    claim matches `expected_type`.

    Raises:
        TokenExpiredError: the signature is valid but `exp` has passed.
        InvalidTokenError: bad signature, wrong `type`, or a missing/malformed
            required claim (`sub`, `jti`).
    """
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Your session has expired. Please log in again.") from exc
    except JWTError as exc:
        logger.info("JWT decode failed: %s", exc)
        raise InvalidTokenError("Invalid authentication token.") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise InvalidTokenError(f"Expected a '{expected_type}' token but received a '{token_type}' token.")

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise InvalidTokenError("Authentication token is missing its subject claim.")
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError("Authentication token subject is malformed.") from exc

    raw_jti = payload.get("jti")
    if not raw_jti:
        raise InvalidTokenError("Authentication token is missing its jti claim.")

    exp_claim = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_claim, tz=timezone.utc) if exp_claim else None

    return TokenData(user_id=user_id, email=payload.get("email"), jti=str(raw_jti), exp=expires_at)


def decode_access_token(token: str, settings: Settings | None = None) -> TokenData:
    """Convenience wrapper: `decode_token(token, expected_type="access")`."""
    return decode_token(token, expected_type="access", settings=settings)


def decode_refresh_token(token: str, settings: Settings | None = None) -> TokenData:
    """Convenience wrapper: `decode_token(token, expected_type="refresh")`."""
    return decode_token(token, expected_type="refresh", settings=settings)
