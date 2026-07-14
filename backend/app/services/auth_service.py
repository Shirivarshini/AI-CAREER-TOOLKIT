"""
Auth service — registration, authentication, session & token business logic.

Why this file exists
---------------------
Coordinates `UserRepository` (persistence), `TokenBlacklistRepository`
(revocation), and `app.core.security` (hashing/JWT) without any of those
concerns leaking into the API router, matching the pattern established
by `ResumeService` and `GitHubAnalysisService`. The router stays a thin
HTTP adapter; this is where the "recipe" for signup/login/refresh/logout
lives.

How it works
------------
`AuthService.register_user()`:
  1. Looks up the email; raises `ConflictError` (-> HTTP 409) if it's
     already taken.
  2. Hashes the password (never stores plaintext) and persists the user.

`AuthService.authenticate_user()`:
  1. Looks up the email; raises `UnauthorizedError` (-> HTTP 401) if no
     account exists *or* the password doesn't match — intentionally the
     same error either way, so a login attempt can't be used to enumerate
     which emails are registered.
  2. Also rejects a correct password on a deactivated (`is_active=False`)
     account.

`AuthService.issue_token()` mints an access+refresh pair (see
`app.core.security`) and wraps them in the `Token` response schema —
used by both login and refresh (a refresh always returns a *new* pair,
i.e. refresh-token rotation, not just a new access token).

`AuthService.refresh_access_token()`:
  1. Decodes the incoming refresh token (rejecting anything that isn't a
     valid, unexpired `type="refresh"` token).
  2. Rejects it if its `jti` has already been blacklisted (used once via
     rotation, or explicitly revoked via logout).
  3. Re-loads the user and re-checks `is_active` — a deactivated account
     cannot mint new access tokens even with a still-valid refresh token.
  4. Blacklists the *old* refresh token's `jti` (rotation: each refresh
     token is single-use) and issues a brand-new access+refresh pair.

`AuthService.logout()` blacklists the current access token's `jti` for
its remaining lifetime, and — if the client also sends its refresh
token — blacklists that too, so a stolen refresh token can't outlive an
explicit logout.

Where future code should go
----------------------------
Password-reset and email-verification flows are natural siblings here:
mint a short-lived, single-purpose token via `app.core.security`
(`type="password_reset"` / `"email_verification"`), email it to the
user, and add a `confirm_password_reset()` / `confirm_email_verification()`
method that decodes it, blacklists it (single-use, same as refresh
rotation), and updates the `User` row (`hashed_password` / `is_verified`)
via `UserRepository`. No changes to the token or blacklist machinery are
needed for either.
"""

import logging
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import ConflictError, TokenRevokedError, UnauthorizedError
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, hash_password, verify_password
from app.models.user import User
from app.repositories.token_blacklist_repository import TokenBlacklistRepository, get_token_blacklist_repository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import Token, TokenData, UserCreate, UserLogin

logger = logging.getLogger(__name__)


class AuthService:
    """Orchestrates user registration, authentication, and session/token lifecycle."""

    def __init__(
        self,
        repository: UserRepository,
        settings: Settings,
        blacklist: TokenBlacklistRepository,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._blacklist = blacklist

    # --- Registration & authentication --------------------------------

    async def register_user(self, payload: UserCreate) -> User:
        """
        Create a new user account.

        Raises:
            ConflictError: an account with this email already exists.
        """
        existing = await self._repository.get_by_email(payload.email)
        if existing is not None:
            raise ConflictError("An account with this email address already exists.")

        hashed = hash_password(payload.password)
        user = await self._repository.create(
            full_name=payload.full_name,
            email=payload.email,
            hashed_password=hashed,
        )
        logger.info("Registered new user '%s'", user.email)
        return user

    async def authenticate_user(self, payload: UserLogin) -> User:
        """
        Validate email/password credentials.

        Raises:
            UnauthorizedError: no matching account, wrong password, or
                the account has been deactivated.
        """
        user = await self._repository.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedError("Incorrect email or password.")
        if not user.is_active:
            raise UnauthorizedError("This account has been deactivated.")
        return user

    # --- Token issuance / refresh / revocation -------------------------

    def issue_token(self, user: User) -> Token:
        """Mint a fresh access+refresh token pair for an already-authenticated user."""
        access_token, expires_in = create_access_token(
            user_id=user.id, email=user.email, settings=self._settings
        )
        refresh_token, _ = create_refresh_token(
            user_id=user.id, email=user.email, settings=self._settings
        )
        return Token(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    async def refresh_access_token(self, refresh_token: str) -> Token:
        """
        Exchange a valid, non-revoked refresh token for a brand-new
        access+refresh pair, rotating (single-use) the old refresh token.

        Raises:
            TokenExpiredError / InvalidTokenError: from `decode_refresh_token`
                (propagated from `app.core.security`) if the token is
                malformed, wrongly-typed, or expired.
            TokenRevokedError: the refresh token was already used
                (rotation) or explicitly logged out.
            UnauthorizedError: the user no longer exists or was deactivated.
        """
        token_data = decode_refresh_token(refresh_token, settings=self._settings)

        if await self._blacklist.is_blacklisted(token_data.jti):
            raise TokenRevokedError("This refresh token has already been used or revoked.")

        user = await self._repository.get_by_id(token_data.user_id)
        if user is None:
            raise UnauthorizedError("The user for this token no longer exists.")
        if not user.is_active:
            raise UnauthorizedError("This account has been deactivated.")

        await self._blacklist_current_token(token_data)

        logger.info("Rotated refresh token for user '%s'", user.email)
        return self.issue_token(user)

    async def logout(self, access_token_data: TokenData, refresh_token: str | None) -> None:
        """
        Revoke the current session: blacklist the access token in use for
        this request, and — if provided — the refresh token too, so
        neither can be replayed after logout even though JWTs are
        otherwise stateless.
        """
        await self._blacklist_current_token(access_token_data)

        if refresh_token:
            refresh_token_data = decode_refresh_token(refresh_token, settings=self._settings)
            await self._blacklist_current_token(refresh_token_data)

        logger.info("Logged out user id '%s'", access_token_data.user_id)

    async def _blacklist_current_token(self, token_data: TokenData) -> None:
        """Blacklist `token_data.jti` for its remaining lifetime (never negative)."""
        if token_data.jti is None:
            return
        ttl_seconds = 0
        if token_data.exp is not None:
            ttl_seconds = int((token_data.exp - datetime.now(timezone.utc)).total_seconds())
        await self._blacklist.blacklist(token_data.jti, ttl_seconds)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    blacklist: TokenBlacklistRepository = Depends(get_token_blacklist_repository),
) -> AuthService:
    """FastAPI dependency factory for AuthService — one per request, DB-session-scoped."""
    return AuthService(repository=UserRepository(db), settings=get_settings(), blacklist=blacklist)
