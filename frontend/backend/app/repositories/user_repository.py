"""
User repository — database access for the `users` table.

Why this file exists
---------------------
Clean architecture calls for isolating persistence details behind a
repository so the service layer (`AuthService`) never issues raw
SQLAlchemy queries itself. This is a *database* repository (unlike
`app/repositories/resume_file_repository.py`, which handles temporary
filesystem storage) — it's the first one in the project, since Auth is
the first module that needs a real DB-backed table.

How it works
------------
- Takes an `AsyncSession` (from `app.core.database.get_db`) injected by
  the caller — the repository itself never opens/closes sessions, so a
  request's session lifecycle stays owned by the FastAPI dependency.
- `get_by_email` is the lookup both signup (uniqueness check) and login
  (credential lookup) need.
- `create` persists a new user and returns the refreshed ORM instance
  (so generated fields — `id`, `created_at`, `updated_at` — are
  populated for the caller to map into a response schema).

Where future code should go
----------------------------
Additional queries (e.g. `update_password`, `mark_verified`,
`deactivate`) belong here as new methods — services should never touch
`AsyncSession` directly.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Database access for `User` rows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, *, full_name: str, email: str, hashed_password: str) -> User:
        user = User(full_name=full_name, email=email, hashed_password=hashed_password)
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return user
