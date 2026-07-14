"""
Dashboard repository — database access spanning the four analysis tables.

Why this file exists
---------------------
Unlike every other repository in this project (one table each), the
Dashboard has to read *across* `ResumeAnalysis`, `GitHubAnalysis`,
`LinkedInAnalysis`, and `SkillGapResult` and present them as one merged
timeline (PRD: "Recent Activities", "Last Analysis Date", and the
paginated history list). Rather than fetch each table separately and
merge/sort/paginate in Python (which breaks `LIMIT`/`OFFSET` the moment
there's more than one page), this repository builds a single `UNION ALL`
query with a matching column shape per table, so pagination and ordering
happen in the database.

How it works
------------
- `_history_union()` builds the shared subquery: each table contributes
  `(id, analysis_type, title, score, created_at)`, filtered to the
  requesting user. `title` is the closest human-readable label each
  table has (filename / GitHub username / target role); `LinkedInAnalysis`
  has no natural title column, so a fixed label is used. `SkillGapResult`
  has no single "score" column, so `NULL` is projected in its place —
  matching `ActivityItem.score: float | None` on the schema side.
- `count_by_type()` / `list_recent()` / `list_history()` all read from
  that union. `get_by_id()` / `delete_by_id()` instead query each table
  directly (in a fixed, cheap order) since the caller has one id and
  doesn't know which table it belongs to — the union isn't needed there.
- Every method takes `user_id` and scopes every query to it, so one
  user's dashboard can never read or delete another user's analysis
  (enforced here, not just in the service layer).

Where future code should go
----------------------------
If a fifth analysis type is ever added, add its `SELECT` branch to
`_history_union()` and its own direct-lookup branch to `get_by_id()` /
`delete_by_id()`, matching the existing four.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import GitHubAnalysis, LinkedInAnalysis, ResumeAnalysis, SkillGapResult
from app.schemas.dashboard import AnalysisType


class DashboardRepository:
    """Database access spanning `ResumeAnalysis`, `GitHubAnalysis`, `LinkedInAnalysis`, `SkillGapResult`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _history_union(self, user_id: uuid.UUID):
        """Build the `UNION ALL` subquery of every analysis type, scoped to `user_id`."""
        resume = select(
            ResumeAnalysis.id.label("id"),
            literal(AnalysisType.RESUME.value).label("analysis_type"),
            ResumeAnalysis.filename.label("title"),
            ResumeAnalysis.ats_score.label("score"),
            ResumeAnalysis.created_at.label("created_at"),
        ).where(ResumeAnalysis.user_id == user_id)

        github = select(
            GitHubAnalysis.id.label("id"),
            literal(AnalysisType.GITHUB.value).label("analysis_type"),
            GitHubAnalysis.username.label("title"),
            GitHubAnalysis.score.label("score"),
            GitHubAnalysis.created_at.label("created_at"),
        ).where(GitHubAnalysis.user_id == user_id)

        linkedin = select(
            LinkedInAnalysis.id.label("id"),
            literal(AnalysisType.LINKEDIN.value).label("analysis_type"),
            literal("LinkedIn Profile Optimization").label("title"),
            LinkedInAnalysis.score.label("score"),
            LinkedInAnalysis.created_at.label("created_at"),
        ).where(LinkedInAnalysis.user_id == user_id)

        skill_gap = select(
            SkillGapResult.id.label("id"),
            literal(AnalysisType.SKILL_GAP.value).label("analysis_type"),
            SkillGapResult.target_role.label("title"),
            SkillGapResult.score.label("score"),
            SkillGapResult.created_at.label("created_at"),
        ).where(SkillGapResult.user_id == user_id)

        return union_all(resume, github, linkedin, skill_gap).subquery("history")

    async def count_by_type(self, user_id: uuid.UUID) -> dict[AnalysisType, int]:
        """Return the row count for each analysis type, scoped to `user_id`."""

        async def _count(model, column) -> int:
            result = await self._db.execute(
                select(func.count()).select_from(model).where(column == user_id)
            )
            return int(result.scalar_one())

        return {
            AnalysisType.RESUME: await _count(ResumeAnalysis, ResumeAnalysis.user_id),
            AnalysisType.GITHUB: await _count(GitHubAnalysis, GitHubAnalysis.user_id),
            AnalysisType.LINKEDIN: await _count(LinkedInAnalysis, LinkedInAnalysis.user_id),
            AnalysisType.SKILL_GAP: await _count(SkillGapResult, SkillGapResult.user_id),
        }

    async def get_last_analysis_date(self, user_id: uuid.UUID) -> datetime | None:
        """Return the most recent `created_at` across all four tables, or None if the user has no history."""
        history = self._history_union(user_id)
        result = await self._db.execute(select(func.max(history.c.created_at)))
        return result.scalar_one_or_none()

    async def list_recent(self, user_id: uuid.UUID, limit: int) -> list:
        """Return the `limit` most recent rows across all four tables, newest first."""
        history = self._history_union(user_id)
        stmt = select(history).order_by(history.c.created_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.all())

    async def list_history(self, user_id: uuid.UUID, limit: int, offset: int) -> tuple[list, int]:
        """Return a page of merged history rows (newest first) plus the total matching count."""
        history = self._history_union(user_id)

        count_result = await self._db.execute(select(func.count()).select_from(history))
        total = int(count_result.scalar_one())

        stmt = select(history).order_by(history.c.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.all()), total

    async def get_by_id(self, user_id: uuid.UUID, analysis_id: uuid.UUID):
        """
        Look up a single analysis by id, scoped to `user_id`, across all four
        tables. Returns a `(model_instance, AnalysisType)` tuple, or `None`
        if no matching row is owned by this user in any table.
        """
        lookups = (
            (ResumeAnalysis, AnalysisType.RESUME),
            (GitHubAnalysis, AnalysisType.GITHUB),
            (LinkedInAnalysis, AnalysisType.LINKEDIN),
            (SkillGapResult, AnalysisType.SKILL_GAP),
        )
        for model, analysis_type in lookups:
            result = await self._db.execute(
                select(model).where(model.id == analysis_id, model.user_id == user_id)
            )
            instance = result.scalar_one_or_none()
            if instance is not None:
                return instance, analysis_type
        return None

    async def delete_by_id(self, user_id: uuid.UUID, analysis_id: uuid.UUID) -> AnalysisType | None:
        """Delete a single analysis by id, scoped to `user_id`. Returns its type, or None if not found."""
        found = await self.get_by_id(user_id, analysis_id)
        if found is None:
            return None
        instance, analysis_type = found
        await self._db.delete(instance)
        await self._db.commit()
        return analysis_type
