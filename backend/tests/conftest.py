"""
Shared pytest fixtures.

Why this file exists
---------------------
Provides a reusable async HTTP test client for exercising the FastAPI app
in-process (no real network/socket), following FastAPI's recommended
`httpx.AsyncClient` + `ASGITransport` pattern.

Where future code should go
----------------------------
Later modules (DB-backed tests) should add a fixture here that spins up
a test database / transaction-per-test rollback, e.g. `db_session`,
and override the `get_db` dependency on the app for isolated test runs.
"""

from typing import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
