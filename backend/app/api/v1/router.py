"""
Version-1 API router aggregator.

Why this file exists
---------------------
Rather than registering every feature router directly on the `FastAPI`
app instance in `main.py`, we aggregate them under a single versioned
`api_router` here. This keeps versioning explicit (all v1 endpoints live
under `/api/v1/...`) and makes `main.py` agnostic to how many feature
routers exist.

How it works
------------
Each feature module exposes its own `APIRouter` (see `health.py` for the
pattern). This file imports and `include_router()`s each one, optionally
with its own `prefix` and `tags` for Swagger UI grouping.

Where future code should go
----------------------------
As each feature module is built, add a line here, e.g.:

    from app.api.v1 import reports
    api_router.include_router(reports.router, prefix="/report", tags=["Report Service"])
"""

from fastapi import APIRouter

from app.api.v1 import auth, dashboard, github, health, linkedin, resume, skill_gap

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(resume.router, prefix="/resume")
api_router.include_router(github.router, prefix="/github")
api_router.include_router(skill_gap.router, prefix="/skills")
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(linkedin.router, prefix="/linkedin")
api_router.include_router(dashboard.router, prefix="/dashboard")
