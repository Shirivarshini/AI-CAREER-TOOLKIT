"""
User Dashboard — service layer.

Why this file exists
---------------------
The service layer coordinates `DashboardRepository` and maps its raw
rows/ORM instances onto the API's Pydantic schemas — without any of that
mapping logic leaking into the router, matching the pattern established
by `ResumeService` / `GitHubAnalysisService`.

How it works
------------
`DashboardService`:
  - `get_summary()` -> per-type counts, the most recent activity, and the
    last-analysis timestamp (PRD: "Dashboard should return").
  - `get_history()` -> a paginated, merged view of all four analysis
    types, newest first.
  - `get_analysis_detail()` -> a single analysis's full stored result,
    raising `NotFoundError` if it doesn't exist or isn't owned by the
    requesting user.
  - `delete_analysis()` -> removes a single analysis, same ownership/
    not-found semantics as `get_analysis_detail()`.

Every method is scoped to the authenticated user's id, enforced at the
repository's query level (see `DashboardRepository`), so this service
never has to separately check ownership after the fact.

Where future code should go
----------------------------
Additional dashboard views (e.g. a score-trend series) get their own
method here, reusing `DashboardRepository`'s existing union query where
possible rather than adding new per-table queries.
"""

import logging
import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.analysis import GitHubAnalysis, LinkedInAnalysis, ResumeAnalysis, SkillGapResult
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    ActivityItem,
    AnalysisDetail,
    AnalysisType,
    DashboardCounts,
    DashboardSummaryResponse,
    DeleteAnalysisResponse,
    PaginatedHistoryResponse,
)

logger = logging.getLogger(__name__)

_LINKEDIN_TITLE = "LinkedIn Profile Optimization"

# Default / max page size for GET /dashboard/history, and the number of
# rows shown under the summary's "Recent Activities".
DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100
RECENT_ACTIVITIES_LIMIT = 5


class DashboardService:
    """Orchestrates dashboard summary/history/detail reads and history deletion."""

    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    async def get_summary(self, user_id: uuid.UUID) -> DashboardSummaryResponse:
        counts = await self._repository.count_by_type(user_id)
        recent_rows = await self._repository.list_recent(user_id, RECENT_ACTIVITIES_LIMIT)
        last_analysis_date = await self._repository.get_last_analysis_date(user_id)

        return DashboardSummaryResponse(
            counts=DashboardCounts(
                total_resume_analyses=counts[AnalysisType.RESUME],
                total_github_analyses=counts[AnalysisType.GITHUB],
                total_linkedin_optimizations=counts[AnalysisType.LINKEDIN],
                total_skill_gap_analyses=counts[AnalysisType.SKILL_GAP],
            ),
            recent_activities=[self._map_history_row(row) for row in recent_rows],
            last_analysis_date=last_analysis_date,
        )

    async def get_history(
        self, user_id: uuid.UUID, limit: int = DEFAULT_HISTORY_LIMIT, offset: int = 0
    ) -> PaginatedHistoryResponse:
        bounded_limit = max(1, min(limit, MAX_HISTORY_LIMIT))
        bounded_offset = max(0, offset)

        rows, total = await self._repository.list_history(user_id, bounded_limit, bounded_offset)
        return PaginatedHistoryResponse(
            items=[self._map_history_row(row) for row in rows],
            total=total,
            limit=bounded_limit,
            offset=bounded_offset,
        )

    async def get_analysis_detail(self, user_id: uuid.UUID, analysis_id: uuid.UUID) -> AnalysisDetail:
        found = await self._repository.get_by_id(user_id, analysis_id)
        if found is None:
            raise NotFoundError("No analysis was found with that id for the current user.")
        instance, analysis_type = found
        return self._map_detail(instance, analysis_type)

    async def delete_analysis(self, user_id: uuid.UUID, analysis_id: uuid.UUID) -> DeleteAnalysisResponse:
        analysis_type = await self._repository.delete_by_id(user_id, analysis_id)
        if analysis_type is None:
            raise NotFoundError("No analysis was found with that id for the current user.")
        logger.info("Deleted %s analysis %s for user %s", analysis_type.value, analysis_id, user_id)
        return DeleteAnalysisResponse(id=analysis_id, analysis_type=analysis_type)

    @staticmethod
    def _map_history_row(row) -> ActivityItem:
        """Map one row of `DashboardRepository`'s merged union query onto `ActivityItem`."""
        return ActivityItem(
            id=row.id,
            analysis_type=AnalysisType(row.analysis_type),
            title=row.title,
            score=row.score,
            created_at=row.created_at,
        )

    @staticmethod
    def _map_detail(instance, analysis_type: AnalysisType) -> AnalysisDetail:
        """Map a single ORM instance (one of the four analysis models) onto `AnalysisDetail`."""
        if isinstance(instance, ResumeAnalysis):
            title, score, result = instance.filename, instance.ats_score, instance.breakdown_json
        elif isinstance(instance, GitHubAnalysis):
            title, score, result = instance.username, instance.score, instance.breakdown_json
        elif isinstance(instance, LinkedInAnalysis):
            title, score, result = _LINKEDIN_TITLE, instance.score, instance.breakdown_json
        elif isinstance(instance, SkillGapResult):
            title, score, result = (
                instance.target_role,
                instance.score,
                {"matched_skills": instance.matched_skills, "missing_skills": instance.missing_skills},
            )
        else:  # pragma: no cover - defensive, unreachable given the four lookups above
            raise NotFoundError("No analysis was found with that id for the current user.")

        return AnalysisDetail(
            id=instance.id,
            analysis_type=analysis_type,
            title=title,
            score=score,
            created_at=instance.created_at,
            result=result,
        )


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    """FastAPI dependency factory for DashboardService — one per request, DB-session-scoped."""
    return DashboardService(repository=DashboardRepository(db))
