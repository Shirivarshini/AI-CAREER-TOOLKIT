"""
Authentication dependencies — the reusable `Depends(...)` building blocks
every protected route (in this module and future ones) attaches.

Why this file exists
---------------------
FastAPI's idiomatic way to protect routes is dependency injection, not a
global middleware: some routes must stay public (`/auth/signup`,
`/auth/login`, `/auth/refresh`, `/health`, and — per the PRD — resume/
GitHub/skill-gap analysis, which explicitly support a guest mode). A
blanket middleware would either have to hardcode a list of public paths
(fragile, easy to forget when adding a new public route) or enforce auth
everywhere and require per-route opt-*out* (a worse default for a guest-
mode-first product). Per-route `Depends(...)` is explicit at the route
definition and is what the task's "Protect routes using JWT
authentication" is designed around — see the "Where future code should
go" note below for the middleware alternative that was considered and
not used.

How it works
------------
- `oauth2_scheme` is a standard `OAuth2PasswordBearer`, pointed at
  `/auth/login` purely so Swagger UI's "Authorize" button and OpenAPI
  clients know where a token comes from — it does not call that endpoint
  itself. It extracts the `Authorization: Bearer <token>` header and
  raises FastAPI's own 401 if the header is missing entirely.
- `get_current_token_data` decodes the bearer token (via
  `app.core.security.decode_access_token` — raising `TokenExpiredError`/
  `InvalidTokenError` on a bad token, both handled globally by
  `app/middlewares/error_handler.py`) and rejects it if its `jti` is on
  the blacklist (`TokenRevokedError` — e.g. after logout). This is also
  reused directly by the logout endpoint, which needs the raw
  `TokenData` (not just the `User`) to know which `jti`/`exp` to
  blacklist.
- `get_current_user` builds on that to load the actual `User` row —
  this is the one most routes will depend on.
- `get_current_active_user` adds the `is_active` check on top — routes
  that should reject a deactivated account (nearly everything) depend on
  this one instead of `get_current_user` directly.

Where future code should go
----------------------------
If a future requirement needs role-based access control (e.g. an admin-
only route), add a `require_role(role: str)` dependency factory here
that wraps `get_current_active_user` — do not scatter role checks across
individual routers.

On the "middleware" question noted above: if per-request *observability*
(e.g. attaching the authenticated user id to every log line, even on
routes that don't require auth) is ever wanted, that's a legitimate use
of a lightweight, best-effort middleware — decode the token if present,
attach `request.state.user_id`, never raise. That would sit in
`app/middlewares/`, alongside `RequestLoggingMiddleware`, and would be
additive to (not a replacement for) the dependencies below, which remain
the actual enforcement mechanism.
"""

import logging

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.database import get_db
from app.core.exceptions import AppException, ForbiddenError, TokenRevokedError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.token_blacklist_repository import TokenBlacklistRepository, get_token_blacklist_repository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)

_settings = get_settings()

# tokenUrl is relative to the OpenAPI server root and only used by API docs /
# client tooling to know where to obtain a token — this dependency never
# calls it itself.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{_settings.API_V1_PREFIX}/auth/login")


async def get_current_token_data(
    token: str = Depends(oauth2_scheme),
    blacklist: TokenBlacklistRepository = Depends(get_token_blacklist_repository),
) -> TokenData:
    """
    Decode and validate the bearer access token, rejecting anything
    expired, malformed, or revoked (blacklisted).

    Exposed as its own dependency (rather than folded into
    `get_current_user`) because the logout endpoint needs the raw
    `jti`/`exp` to blacklist — not a loaded `User`.
    """
    token_data = decode_access_token(token)
    if token_data.jti and await blacklist.is_blacklisted(token_data.jti):
        raise TokenRevokedError("This session has been logged out. Please log in again.")
    return token_data


async def get_current_user(
    token_data: TokenData = Depends(get_current_token_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Load the `User` identified by a validated access token."""
    repository = UserRepository(db)
    user = await repository.get_by_id(token_data.user_id)
    if user is None:
        raise UnauthorizedError("The user for this token no longer exists.")
    return user


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    """`get_current_user`, plus rejecting a deactivated account."""
    if not user.is_active:
        raise ForbiddenError("This account has been deactivated.")
    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    blacklist: TokenBlacklistRepository = Depends(get_token_blacklist_repository),
) -> User | None:
    """
    Best-effort variant of `get_current_user`, for the guest-mode analysis
    routes (Resume, GitHub, LinkedIn, Skill-Gap) that persist a report of
    every analysis they run.

    Those routes have never required authentication (per the PRD's guest
    mode) and must keep working exactly as before for anonymous callers —
    so, unlike `get_current_user`, this dependency never raises. No
    `Authorization` header, a malformed one, an expired/invalid/blacklisted
    token, or a token for a deleted/deactivated user all resolve the same
    way: `None` (the report is saved with a null `user_id`, same as today's
    guest-mode default). Only a fully valid, active-user token resolves to
    a `User`, so the resulting report can be attributed to their account.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        token_data: TokenData = decode_access_token(token)
        if token_data.user_id is None:
            return None
        if token_data.jti and await blacklist.is_blacklisted(token_data.jti):
            return None
        user = await UserRepository(db).get_by_id(token_data.user_id)
    except AppException:
        return None

    if user is None or not user.is_active:
        return None
    return user
