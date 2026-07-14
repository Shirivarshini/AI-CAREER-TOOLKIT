"""
Tests for the Auth module (POST /api/v1/auth/signup, /login).

Unlike `test_github.py` (which mocks an external HTTP API), this module
is DB-backed, and the project doesn't yet have a test-database fixture
(see the note in `conftest.py`: "Later modules (DB-backed tests) should
add a fixture here"). Rather than stand up a real Postgres instance or
add a new test-only dependency (e.g. aiosqlite) as part of this module,
these tests exercise `AuthService` directly against a small in-memory
fake repository that satisfies the same interface as
`UserRepository` — this covers the actual business logic (duplicate-email
rejection, password verification, token issuance) without a live database.

Run with:
    pytest -v tests/test_auth.py
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.config.settings import get_settings
from app.core.cache import InMemoryCacheBackend
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.schemas.auth import UserCreate, UserLogin
from app.services.auth_service import AuthService


class FakeUserRepository:
    """In-memory stand-in for `UserRepository`, keyed by email."""

    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((u for u in self._by_email.values() if u.id == user_id), None)

    async def create(self, *, full_name: str, email: str, hashed_password: str) -> User:
        now = datetime.now(timezone.utc)
        user = User(
            id=uuid.uuid4(),
            full_name=full_name,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=False,
            created_at=now,
            updated_at=now,
        )
        self._by_email[email] = user
        return user


@pytest.fixture
def auth_service() -> AuthService:
    blacklist = TokenBlacklistRepository(cache=InMemoryCacheBackend())
    return AuthService(repository=FakeUserRepository(), settings=get_settings(), blacklist=blacklist)


@pytest.mark.asyncio
async def test_register_user_success(auth_service: AuthService) -> None:
    payload = UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")

    user = await auth_service.register_user(payload)

    assert user.email == "priya@example.com"
    assert user.full_name == "Priya Sharma"
    assert user.hashed_password != "SecurePass123"  # never stored in plaintext
    assert user.is_active is True
    assert user.is_verified is False


@pytest.mark.asyncio
async def test_register_user_duplicate_email_raises_conflict(auth_service: AuthService) -> None:
    payload = UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    await auth_service.register_user(payload)

    with pytest.raises(ConflictError):
        await auth_service.register_user(
            UserCreate(full_name="Someone Else", email="priya@example.com", password="AnotherPass123")
        )


@pytest.mark.asyncio
async def test_authenticate_user_success(auth_service: AuthService) -> None:
    await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )

    user = await auth_service.authenticate_user(
        UserLogin(email="priya@example.com", password="SecurePass123")
    )

    assert user.email == "priya@example.com"


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password_raises_unauthorized(auth_service: AuthService) -> None:
    await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )

    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_user(
            UserLogin(email="priya@example.com", password="WrongPassword")
        )


@pytest.mark.asyncio
async def test_authenticate_user_unknown_email_raises_unauthorized(auth_service: AuthService) -> None:
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_user(
            UserLogin(email="nobody@example.com", password="Whatever123")
        )


@pytest.mark.asyncio
async def test_authenticate_user_deactivated_account_raises_unauthorized(
    auth_service: AuthService,
) -> None:
    user = await auth_service.register_user(
        UserCreate(full_name="Priya Sharma", email="priya@example.com", password="SecurePass123")
    )
    user.is_active = False

    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_user(
            UserLogin(email="priya@example.com", password="SecurePass123")
        )


def test_issue_token_returns_bearer_token(auth_service: AuthService) -> None:
    user = User(
        id=uuid.uuid4(),
        full_name="Priya Sharma",
        email="priya@example.com",
        hashed_password=hash_password("SecurePass123"),
        is_active=True,
        is_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    token = auth_service.issue_token(user)

    assert token.token_type == "bearer"
    assert token.expires_in > 0
    assert len(token.access_token.split(".")) == 3  # header.payload.signature
    assert len(token.refresh_token.split(".")) == 3
    assert token.access_token != token.refresh_token
