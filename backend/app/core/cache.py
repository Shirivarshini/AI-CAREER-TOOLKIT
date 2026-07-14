"""
Cache backend abstraction — in-process today, Redis-ready by construction.

Why this file exists
---------------------
The GitHub Analysis module (and, later, LinkedIn/Skill-Gap) calls slow,
rate-limited third-party APIs. The PRD explicitly names Redis as the
caching layer ("GitHub API response caching, rate-limit tracking") but
also marks it optional/deferred (`REDIS_ENABLED` defaults to `False`,
per `.env.example`). Rather than block the GitHub module on standing up
Redis, we define a small `CacheBackend` interface now and depend on that
interface everywhere — the concrete backend is swapped via configuration,
not code changes, once Redis is actually deployed.

How it works
------------
- `CacheBackend` is the interface every backend implements: `get`, `set`,
  `delete`. Keys and values are plain strings — callers (services) are
  responsible for their own serialization (e.g. `model_dump_json()`),
  matching how a real Redis client behaves.
- `InMemoryCacheBackend` is a process-local dict with per-key TTL. It is
  the default (`REDIS_ENABLED=false`) and is what tests run against —
  no external service required, no test mocking of Redis needed.
- `RedisCacheBackend` wraps `redis.asyncio.Redis`, used automatically the
  moment `REDIS_ENABLED=true` and `REDIS_URL` point at a real instance.
  It is not exercised by the default test suite (no Redis in CI), but is
  wired end-to-end and ready to flip on.
- `get_cache_backend()` is an `lru_cache`-d factory (same pattern as
  `get_settings()`), so the whole process shares one backend instance
  and, for `RedisCacheBackend`, one connection pool.

Where future code should go
----------------------------
Any service that wants to cache a slow/rate-limited external lookup
should depend on `CacheBackend` (via `Depends(get_cache_backend)` or a
plain factory call, matching how `GitHubAnalysisService` does it) rather
than importing `redis` directly. If a new backend (e.g. an in-memory LRU
with size limits, or DynamoDB) is needed later, implement `CacheBackend`
and select it in `get_cache_backend()` — callers never change.
"""

import logging
import time
from abc import ABC, abstractmethod
from functools import lru_cache

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Interface every cache backend implements. Values are plain strings."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the cached value for `key`, or None if missing/expired."""
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store `value` under `key`, expiring after `ttl_seconds`."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove `key` from the cache, if present."""
        raise NotImplementedError


class InMemoryCacheBackend(CacheBackend):
    """
    Process-local cache backend with per-key expiry.

    Suitable for a single-process MVP deployment and for tests. Not shared
    across multiple app instances/workers — that's exactly the gap
    `RedisCacheBackend` fills once enabled.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}  # key -> (expires_at_monotonic, value)

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + max(ttl_seconds, 0), value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class RedisCacheBackend(CacheBackend):
    """
    Redis-backed cache backend, used once `REDIS_ENABLED=true`.

    Uses `redis.asyncio` (already a project dependency) so no additional
    package is required. The connection is lazy — `redis.asyncio.Redis`
    does not open a socket until the first command — so constructing this
    class has no I/O cost even if Redis is temporarily unreachable.
    """

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as redis  # local import: keep redis optional at module load time

        self._client = redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._client.set(key, value, ex=max(ttl_seconds, 1))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)


def _build_cache_backend(settings: Settings) -> CacheBackend:
    if settings.REDIS_ENABLED:
        logger.info("Cache backend: Redis (%s)", settings.REDIS_URL)
        return RedisCacheBackend(settings.REDIS_URL)
    logger.info("Cache backend: in-memory (set REDIS_ENABLED=true to use Redis)")
    return InMemoryCacheBackend()


@lru_cache
def get_cache_backend() -> CacheBackend:
    """Return a process-wide cached `CacheBackend` singleton, selected via `Settings`."""
    return _build_cache_backend(get_settings())
