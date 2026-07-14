"""
User model — SQLAlchemy ORM.

Why this file exists
---------------------
Backs the Auth module (PRD section 15's "Open Questions" around auth,
and the `User` entry in the PRD's data model, section 11). This is the
first concrete table in `app/models/`, built on top of the shared
`BaseModelMixin` (UUID primary key + `created_at`) defined in
`app/models/base.py`.

How it works
------------
- Inherits `id` (UUID, primary key) and `created_at` from
  `BaseModelMixin`, and `Base` (the declarative base + Alembic metadata
  target) from `app.core.database`.
- `email` is unique + indexed, since it's the natural login identifier
  and the uniqueness constraint the Auth service relies on to reject
  duplicate signups (see `AuthService.register_user`).
- `hashed_password` never stores a plaintext password — only the bcrypt
  hash produced by `app.core.security.hash_password`.
- `is_active` supports future account deactivation/soft-disable without
  deleting the row. `is_verified` is reserved for a future email/OTP
  verification flow (out of scope for this module, but the column is
  part of the requested schema so later modules don't need a migration
  just to add it).
- `updated_at` is defined directly on this model (rather than added to
  the shared `BaseModelMixin`) since this module only touches the User
  model — the mixin is left as-is for other tables to opt into
  independently.

Where future code should go
----------------------------
Relationships to other tables (e.g. `ResumeAnalysis.user_id`,
`GitHubAnalysis.user_id`) get added as those models are built, each with
a `ForeignKey("users.id")` and a `back_populates`/`relationship` here if
needed.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseModelMixin


class User(Base, BaseModelMixin):
    """A registered user account."""

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r}>"
