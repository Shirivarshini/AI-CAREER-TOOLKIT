"""
User Authentication & Authorization — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: validates the request body/headers, delegates
all real work to `AuthService` (or the `deps.get_current_*` dependencies
for authorization), and wraps results in the standard `SuccessResponse`
envelope — matching the pattern established by `app/api/v1/resume.py`
and `app/api/v1/github.py`. No password hashing, JWT, blacklist, or
persistence logic lives here.

Endpoints
---------
POST /auth/signup   — public. Register a new account.
POST /auth/login    — public. Exchange credentials for an access+refresh
                       token pair.
POST /auth/refresh  — public (the refresh token itself is the
                       credential). Exchange a valid refresh token for a
                       new access+refresh pair (rotation).
POST /auth/logout   — protected. Revoke the current session's access
                       token (and refresh token, if supplied).
GET  /auth/me        — protected. Returns the authenticated user — the
                       task's required protected test endpoint,
                       demonstrating `get_current_active_user` in use.

Note on path prefix: this router is mounted at `/auth` under the
existing versioned API (`/api/v1`, established in Module 1), so the full
paths are `/api/v1/auth/...`. The PRD/task list these as `/api/auth/...`;
the `/v1` segment is our existing versioning convention layered on top
of the same routes — extensible, not conflicting (see the same note in
`resume.py` / `github.py`).

Where future code should go
----------------------------
Password-reset (`POST /auth/password-reset/request`,
`POST /auth/password-reset/confirm`) and email-verification
(`POST /auth/verify-email/confirm`) endpoints get their own `@router`
functions here, calling new `AuthService` methods — see that file's
"Where future code should go" note for the token/service-side design.
"""

import logging

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_active_user, get_current_token_data
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    RefreshTokenRequest,
    Token,
    TokenData,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import AuthService, get_auth_service
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"])


@router.post(
    "/signup",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Creates a new user account with a bcrypt-hashed password. "
        "Returns 409 Conflict if the email address is already registered."
    ),
)
async def signup(
    payload: UserCreate,
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[UserResponse]:
    user = await service.register_user(payload)
    return SuccessResponse(
        message="Account created successfully.",
        data=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=SuccessResponse[Token],
    summary="Authenticate and receive an access + refresh token pair",
    description=(
        "Validates email/password credentials and returns a bearer JWT "
        "access token plus a refresh token on success. Returns 401 "
        "Unauthorized on invalid credentials or a deactivated account."
    ),
)
async def login(
    payload: UserLogin,
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[Token]:
    user = await service.authenticate_user(payload)
    token = service.issue_token(user)
    return SuccessResponse(message="Login successful.", data=token)


@router.post(
    "/refresh",
    response_model=SuccessResponse[Token],
    summary="Exchange a refresh token for a new access + refresh token pair",
    description=(
        "Validates the supplied refresh token and, if it is unexpired and has not "
        "already been used or revoked, issues a brand-new access + refresh token "
        "pair and revokes (rotates) the old refresh token. Returns 401 Unauthorized "
        "if the token is invalid, expired, or already revoked."
    ),
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[Token]:
    token = await service.refresh_access_token(payload.refresh_token)
    return SuccessResponse(message="Token refreshed successfully.", data=token)


@router.post(
    "/logout",
    response_model=SuccessResponse[None],
    summary="Log out and revoke the current session",
    description=(
        "Revokes the access token used to authenticate this request. If a refresh "
        "token is also supplied in the request body, it is revoked too. Both "
        "tokens are blacklisted for their remaining lifetime, so neither can be "
        "replayed after logout even though JWTs are otherwise stateless."
    ),
)
async def logout(
    payload: LogoutRequest,
    token_data: TokenData = Depends(get_current_token_data),
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[None]:
    await service.logout(token_data, payload.refresh_token)
    return SuccessResponse(message="Logged out successfully.", data=None)


@router.get(
    "/me",
    response_model=SuccessResponse[UserResponse],
    summary="Get the currently authenticated user",
    description=(
        "Protected route — requires a valid, non-revoked bearer access token for an "
        "active account. Demonstrates JWT-based route protection via "
        "`get_current_active_user`."
    ),
)
async def read_current_user(
    user: User = Depends(get_current_active_user),
) -> SuccessResponse[UserResponse]:
    return SuccessResponse(message="Current user retrieved successfully.", data=UserResponse.model_validate(user))
