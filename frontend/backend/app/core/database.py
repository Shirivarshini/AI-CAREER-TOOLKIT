"""
Async SQLAlchemy database engine & session management.

Why this file exists
---------------------
Every feature module (Resume, GitHub, LinkedIn, Skill-Gap, Auth) needs a
database session to talk to PostgreSQL. Rather than each module creating
its own engine/session, we centralize engine creation and expose a single
FastAPI dependency (`get_db`) that all routers/repositories use.

How it works
------------
- `engine` is a single, process-wide async SQLAlchemy engine.
- `AsyncSessionLocal` is a session factory bound to that engine.
- `get_db()` is an async generator FastAPI dependency: it yields a session,
  and guarantees it is closed (and rolled back on error) after the request,
  following the "session per request" pattern.
- `Base` is the declarative base that every ORM model (in app/models/)
  must inherit from, so Alembic can autogenerate migrations from metadata.

Where future code should go
----------------------------
- ORM models -> app/models/*.py, importing `Base` from here.
- Repositories -> app/repositories/*.py, depending on `get_db` via
  FastAPI's `Depends(get_db)` (typically injected into a Service, which
  is injected into an API route).
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# `pool_pre_ping` guards against stale connections (e.g. after RDS failover
# or idle timeouts) by testing each connection before it's checked out.
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base class shared by every ORM model in the project."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session scoped to a single
    request, and ensures proper cleanup / rollback on error.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            logger.exception("Database session error — rolling back transaction")
            await session.rollback()
            raise
        finally:
            await session.close()
