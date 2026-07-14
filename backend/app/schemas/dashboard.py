"""
User Dashboard — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the Dashboard module (`GET /dashboard`,
`GET /dashboard/history`, `GET /dashboard/history/{analysis_id}`,
`DELETE /dashboard/history/{analysis_id}`), following the same
per-feature-module pattern as `app/schemas/resume.py` and
`app/schemas/github.py`.

How it works
------------
- `AnalysisType` is the discriminator used everywhere a history item
  needs to say which of the four analysis tables it came from, since
  `GET /dashboard/history` merges rows from `ResumeAnalysis`,
  `GitHubAnalysis`, `LinkedInAnalysis`, and `SkillGapResult` into one
  timeline.
- `ActivityItem` is a lightweight summary row (used by both the
  dashboard summary's "Recent Activities" and the paginated history
  list) — it deliberately excludes the full `breakdown_json`/skills
  payload so the list endpoints stay cheap.
- `AnalysisDetail` is the single-record shape returned by
  `GET /dashboard/history/{analysis_id}`, and includes the full stored
  result payload.
- `DashboardSummaryResponse` maps directly onto PRD section "Dashboard
  should return": per-type totals, recent activity, and the most recent
  analysis date across all four types.

Where future code should go
----------------------------
Additional dashboard views (e.g. score-trend-over-time) get their own
schema here, reusing `AnalysisType` / `ActivityItem` where possible.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisType(str, Enum):
    """Which of the four analysis tables a history/activity row came from."""

    RESUME = "resume"
    GITHUB = "github"
    LINKEDIN = "linkedin"
    SKILL_GAP = "skill_gap"


class ActivityItem(BaseModel):
    """One row in a recent-activity / history list — summary only, no full breakdown."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_type: AnalysisType
    title: str = Field(..., description="Human-readable label, e.g. a filename, username, or target role.")
    score: float | None = Field(None, description="Overall score, if this analysis type has one (Skill-Gap does not).")
    created_at: datetime


class AnalysisDetail(ActivityItem):
    """Full single-record detail, returned by GET /dashboard/history/{analysis_id}."""

    result: dict[str, Any] = Field(
        ..., description="The stored result payload for this analysis (breakdown, or matched/missing skills)."
    )


class PaginatedHistoryResponse(BaseModel):
    """Paginated response for GET /dashboard/history."""

    items: list[ActivityItem]
    total: int = Field(..., ge=0, description="Total number of matching history records across all types.")
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class DashboardCounts(BaseModel):
    """Per-type totals shown on the dashboard summary."""

    total_resume_analyses: int = Field(..., ge=0)
    total_github_analyses: int = Field(..., ge=0)
    total_linkedin_optimizations: int = Field(..., ge=0)
    total_skill_gap_analyses: int = Field(..., ge=0)


class DashboardSummaryResponse(BaseModel):
    """Response for GET /dashboard."""

    counts: DashboardCounts
    recent_activities: list[ActivityItem]
    last_analysis_date: datetime | None = Field(
        None, description="Timestamp of the user's most recent analysis of any type, or null if they have none."
    )


class DeleteAnalysisResponse(BaseModel):
    """Response for DELETE /dashboard/history/{analysis_id}."""

    id: uuid.UUID
    analysis_type: AnalysisType
    deleted: bool = True
