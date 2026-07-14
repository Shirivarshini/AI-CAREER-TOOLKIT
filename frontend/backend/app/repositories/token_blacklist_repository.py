"""
Token blacklist repository — logout / revocation, Redis-ready by
construction.

Why this file exists
---------------------
The task requires a logout endpoint "designed to support future Redis
token blacklisting... reusable interfaces without requiring Redis."
`app/core/cache.py` already defines exactly that kind of interface
(`CacheBackend`, with an in-memory default and a Redis implementation
that activates via `REDIS_ENABLED=true`) for the GitHub Analysis module.
Rather than invent a parallel mechanism, this repository is a thin,
auth-specific wrapper around the same `CacheBackend` — logout support
is "free": flip `REDIS_ENABLED=true` in `.env` and blacklisted tokens are
immediately shared across every app instance/worker, with no code
change here.

How it works
------------
- A token is "blacklisted" by writing its `jti` (JWT ID claim — see
  `app/core/security.py`) as a cache key, with a TTL equal to the
  token's *remaining* lifetime. Once the TTL elapses the underlying JWT
  would have expired anyway, so the blacklist entry can be safely
  forgotten — this keeps the blacklist from growing unbounded.
- `is_blacklisted()` is a simple existence check, called by
  `get_current_token_data` (see `app/api/deps.py`) on every request to a
  protected route, and by `AuthService.refresh_access_token` when
  validating an incoming refresh token.

Where future code should go
----------------------------
Nothing needs to change here for password-reset / email-verification
tokens to support revocation too — they'd reuse `blacklist()` /
`is_blacklisted()` with their own `jti`, the same as access/refresh
tokens.
"""

import logging

from app.core.cache import CacheBackend, get_cache_backend

logger = logging.getLogger(__name__)

_KEY_PREFIX = "blacklisted_token"


class TokenBlacklistRepository:
    """Tracks revoked token `jti`s using the shared `CacheBackend`."""

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    @staticmethod
    def _key(jti: str) -> str:
        return f"{_KEY_PREFIX}:{jti}"

    async def blacklist(self, jti: str, ttl_seconds: int) -> None:
        """
        Mark `jti` as revoked for `ttl_seconds` (normally the token's
        remaining lifetime). A non-positive TTL means the token has
        already expired on its own, so there's nothing to track.
        """
        if ttl_seconds <= 0:
            logger.debug("Skipping blacklist for already-expired jti '%s'", jti)
            return
        await self._cache.set(self._key(jti), "1", ttl_seconds)

    async def is_blacklisted(self, jti: str) -> bool:
        """Return True if `jti` has been revoked and hasn't expired yet."""
        return await self._cache.get(self._key(jti)) is not None


def get_token_blacklist_repository() -> TokenBlacklistRepository:
    """FastAPI dependency factory for TokenBlacklistRepository."""
    return TokenBlacklistRepository(cache=get_cache_backend())
