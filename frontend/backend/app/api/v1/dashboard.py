"""
User Dashboard — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: resolves the authenticated user, delegates all
real work to `DashboardService`, and wraps results in the standard
`SuccessResponse` envelope — matching the pattern established by
`resume.py` / `github.py`. No aggregation, pagination, or mapping logic
lives here.

Endpoints
---------
GET /dashboard
  - Per-type analysis counts, recent activity, and the last analysis
    date for the current user (PRD: "Dashboard should return").
GET /dashboard/history
  - Paginated, merged history across all four analysis types, newest
    first. `limit` (default 20, max 100) / `offset` query params.
GET /dashboard/history/{analysis_id}
  - Full stored result for a single analysis owned by the current user.
DELETE /dashboard/history/{analysis_id}
  - Deletes a single analysis owned by the current user.

Authentication
---------------
Every route depends on `get_current_active_user` (see `app/api/deps.py`)
— the Dashboard has no guest-mode equivalent, since "history" is
meaningless without an account to own it.

Note on path prefix: this router is mounted at `/dashboard` under the
existing versioned API (`/api/v1`), so the full paths are
`/api/v1/dashboard`, `/api/v1/dashboard/history`, and
`/api/v1/dashboard/history/{analysis_id}` — matching the PRD's
`/api/dashboard/...` paths with the project's existing `/v1` versioning
convention layered on top.

Where future code should go
----------------------------
Additional dashboard views (e.g. a score-trend endpoint) get their own
`@router` function in this file.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.dashboard import (
    AnalysisDetail,
    DashboardSummaryResponse,
    DeleteAnalysisResponse,
    PaginatedHistoryResponse,
)
from app.services.dashboard_service import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    DashboardService,
    get_dashboard_service,
)
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["User Dashboard"])


@router.get(
    "",
    response_model=SuccessResponse[DashboardSummaryResponse],
    summary="Get the current user's dashboard summary",
    description=(
        "Returns total Resume, GitHub, LinkedIn, and Skill-Gap analysis counts, "
        "the most recent activities, and the last analysis date for the "
        "authenticated user."
    ),
)
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> SuccessResponse[DashboardSummaryResponse]:
    result = await service.get_summary(current_user.id)
    return SuccessResponse(message="Dashboard summary retrieved successfully.", data=result)


@router.get(
    "/history",
    response_model=SuccessResponse[PaginatedHistoryResponse],
    summary="Get the current user's analysis history",
    description=(
        "Returns a paginated, merged history of every analysis type "
        "(Resume, GitHub, LinkedIn, Skill-Gap) for the authenticated user, "
        "newest first."
    ),
)
async def get_dashboard_history(
    limit: int = Query(DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT, description="Page size."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    current_user: User = Depends(get_current_active_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> SuccessResponse[PaginatedHistoryResponse]:
    result = await service.get_history(current_user.id, limit=limit, offset=offset)
    return SuccessResponse(message="Analysis history retrieved successfully.", data=result)


@router.get(
    "/history/{analysis_id}",
    response_model=SuccessResponse[AnalysisDetail],
    summary="Get a single analysis's full stored result",
    description=(
        "Returns the full stored result for one analysis (any type) owned by "
        "the authenticated user. Raises 404 if it doesn't exist or belongs to "
        "someone else."
    ),
)
async def get_dashboard_history_item(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> SuccessResponse[AnalysisDetail]:
    result = await service.get_analysis_detail(current_user.id, analysis_id)
    return SuccessResponse(message="Analysis retrieved successfully.", data=result)


@router.delete(
    "/history/{analysis_id}",
    response_model=SuccessResponse[DeleteAnalysisResponse],
    summary="Delete a single analysis from history",
    description=(
        "Deletes one analysis (any type) owned by the authenticated user. "
        "Raises 404 if it doesn't exist or belongs to someone else."
    ),
)
async def delete_dashboard_history_item(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> SuccessResponse[DeleteAnalysisResponse]:
    result = await service.delete_analysis(current_user.id, analysis_id)
    return SuccessResponse(message="Analysis deleted successfully.", data=result)
