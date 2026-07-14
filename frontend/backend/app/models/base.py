"""
Shared ORM model mixins.

Why this file exists
---------------------
Every table in the data model (User, ResumeAnalysis, GitHubAnalysis,
LinkedInAnalysis, SkillGapResult — see PRD section 11) needs an `id`
primary key and a `created_at` timestamp. Defining these once as a mixin
avoids repeating the same columns in every model file and keeps the
schema consistent for Alembic autogeneration.

How it works
------------
`TimestampMixin` and `id` are combined into `BaseModelMixin`, which
future ORM models (in later modules) will inherit from alongside
`app.core.database.Base`, e.g.:

    class User(Base, BaseModelMixin):
        __tablename__ = "users"
        email: Mapped[str] = mapped_column(String, unique=True)
        ...

Where future code should go
----------------------------
Actual table models (User, ResumeAnalysis, etc.) belong in this same
`app/models/` package, one file per table/domain (e.g. `user.py`,
`resume_analysis.py`), imported into `app/models/__init__.py` so Alembic's
`env.py` can discover them via `Base.metadata`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class BaseModelMixin:
    """Common columns shared by every table: a UUID primary key + created_at."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
