"""
Health-check endpoint.

Why this file exists
---------------------
Load balancers, ECS/Elastic Beanstalk health checks, and CI smoke tests
all need a lightweight endpoint to confirm the API process is up. This
also serves as the first real endpoint proving the whole stack (config,
routing, schemas, response envelope) is wired correctly before any
business-logic module is built.

Where future code should go
----------------------------
Feature routers go in sibling files in this package, e.g.:
    app/api/v1/resume.py
    app/api/v1/github.py
    app/api/v1/linkedin.py
    app/api/v1/skills.py
    app/api/v1/auth.py
Each exposes an `APIRouter` that gets included in `app/api/v1/router.py`.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config.settings import get_settings
from app.schemas.common import HealthCheckResponse
from app.utils.response import SuccessResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=SuccessResponse[HealthCheckResponse],
    summary="Health check",
    description="Returns basic liveness info. Used by load balancers and uptime monitors.",
)
async def health_check() -> SuccessResponse[HealthCheckResponse]:
    settings = get_settings()
    payload = HealthCheckResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        timestamp=datetime.now(timezone.utc),
    )
    return SuccessResponse(message="Service is healthy.", data=payload)
