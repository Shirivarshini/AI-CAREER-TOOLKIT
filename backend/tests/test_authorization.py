"""
Tests for the authentication/authorization module: `app/core/security.py`
token semantics, `TokenBlacklistRepository`, and `AuthService`'s
refresh/logout flows.

Same approach as `test_auth.py`: no live database or Redis is required.
`AuthService` is exercised against `FakeUserRepository` (imported from
`test_auth.py`) and a real `TokenBlacklistRepository` backed by
`InMemoryCacheBackend` (the same backend the app uses by default when
`REDIS_ENABLED=false`) — so the blacklist logic under test is the real
production code path, just without a live Redis.

Run with:
    pytest -v tests/test_authorization.py
"""

from datetime import timedelta

import pytest

from app.config.settings import get_settings
from app.core.cache import InMemoryCacheBackend
from app.core.exceptions import InvalidTokenError, TokenExpiredError, TokenRevokedError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.schemas.auth import UserCreate
from app.services.auth_service import AuthService
from tests.test_auth import FakeUserRepository

_SETTINGS = get_settings()


# --- app.core.security -------------------------------------------------


def test_access_token_round_trips() -> None:
    import uuid

    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id=user_id, email="priya@example.com")

    token_data = decode_access_token(token)

    assert token_data.user_id == user_id
    assert token_data.email == "priya@example.com"
    assert token_data.jti is not None
    assert expires_in == _SETTINGS.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_refresh_token_round_trips() -> None:
    import uuid

    user_id = uuid.uuid4()
    token, expires_in = create_refresh_token(user_id=user_id, email="priya@example.com")

    token_data = decode_refresh_token(token)

    assert token_data.user_id == user_id
    assert expires_in == _SETTINGS.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def test_access_token_rejected_as_refresh_token() -> None:
    import uuid

    token, _ = create_access_token(user_id=uuid.uuid4(), email="priya@example.com")

    with pytest.raises(InvalidTokenError):
        decode_refresh_token(token)


def test_refresh_token_rejected_as_access_token() -> None:
    import uuid

    token, _ = create_refresh_token(user_id=uuid.uuid4(), email="priya@example.com")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_expired_access_token_raises_token_expired_error() -> None:
    import uuid

    token, _ = create_access_token(
        user_id=uuid.uuid4(), email="priya@example.com", expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_malformed_token_raises_invalid_token_error() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.validtoken")


# --- TokenBlacklistRepository -------------------------------------------


@pytest.mark.asyncio
async def test_blacklist_marks_token_as_revoked() -> None:
    repo = TokenBlacklistRepository(cache=InMemoryCacheBackend())

    assert await repo.is_blacklisted("some-jti") is False

    await repo.blacklist("some-jti", ttl_seconds=60)

    assert await repo.is_blacklisted("some-jti") is True


@pytest.mark.asyncio
async def test_blacklist_skips_already_expired_ttl() -> None:
    repo = TokenBlacklistRepository(cache=InMemoryCacheBackend())

    await repo.blacklist("some-jti", ttl_seconds=0)

    assert await repo.is_blacklisted("some-jti") is False


# --- AuthService: refresh & logout --------------------------------------


@pytest.fixture
def auth_service() -> AuthService:
    blacklist = TokenBlacklistRepository(cache=InMemoryCacheBackend())
    return AuthService(repository=FakeUserRepository(), settings=get_settings(), blacklist=blacklist)


@pytest.mark.asyncio
async def test_refresh_access_token_issues_new_pair(auth_service: AuthService) -> None:
    user = await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )
    original_token = auth_service.issue_token(user)

    new_token = await auth_service.refresh_access_token(original_token.refresh_token)

    assert new_token.access_token != original_token.access_token
    assert new_token.refresh_token != original_token.refresh_token


@pytest.mark.asyncio
async def test_refresh_access_token_rotation_rejects_reuse(auth_service: AuthService) -> None:
    user = await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )
    original_token = auth_service.issue_token(user)

    await auth_service.refresh_access_token(original_token.refresh_token)

    with pytest.raises(TokenRevokedError):
        await auth_service.refresh_access_token(original_token.refresh_token)


@pytest.mark.asyncio
async def test_refresh_access_token_deactivated_account_raises_unauthorized(
    auth_service: AuthService,
) -> None:
    user = await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )
    token = auth_service.issue_token(user)
    user.is_active = False

    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_access_token(token.refresh_token)


@pytest.mark.asyncio
async def test_logout_blacklists_access_and_refresh_tokens(auth_service: AuthService) -> None:
    from app.core.security import decode_access_token as _decode_access

    user = await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )
    token = auth_service.issue_token(user)
    access_token_data = _decode_access(token.access_token)

    await auth_service.logout(access_token_data, token.refresh_token)

    assert await auth_service._blacklist.is_blacklisted(access_token_data.jti) is True
    refresh_token_data = decode_refresh_token(token.refresh_token)
    assert await auth_service._blacklist.is_blacklisted(refresh_token_data.jti) is True
