"""
Shared, reusable Pydantic schemas.

Why this file exists
---------------------
Small, generic schemas used across multiple feature modules (e.g. a
health-check payload, a generic paginated-list wrapper) live here so
feature-specific schema files (`resume.py`, `github.py`, etc., added in
later modules) don't redefine them.

Where future code should go
----------------------------
Feature-specific request/response schemas belong in their own files:
    app/schemas/resume.py
    app/schemas/github.py
    app/schemas/linkedin.py
    app/schemas/skill_gap.py
    app/schemas/auth.py
Only put things here that are genuinely cross-cutting.
"""

from datetime import datetime

from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    """Payload returned by GET /health and /api/v1/health."""

    status: str
    app_name: str
    environment: str
    timestamp: datetime
