"""
Report repositories — database access for the four report tables.

Why this file exists
---------------------
Each analysis service (`ResumeService`, `GitHubAnalysisService`,
`LinkedInService`, `SkillGapService`) needs to persist exactly one thing
after a successful run: a report row. Rather than have each service issue
raw SQLAlchemy inserts, this file gives each one a small, single-purpose
repository — following `app/repositories/user_repository.py`'s pattern
(take an injected `AsyncSession`, expose a `create()` that adds, commits,
refreshes, and returns the row).

How it works
------------
- One repository class per report table, each wrapping exactly one model
  from `app.models.analysis`. `create()`'s keyword-only arguments mirror
  that model's report-relevant columns 1:1 (`user_id`, `analysis_type`,
  `input_data`, the generated result, and score) — `id`/`created_at` are
  populated by `BaseModelMixin`.
- All four repositories commit their own row immediately (rather than
  relying on the caller's later commit), since report-saving is a
  fire-and-forget side effect of a successful analysis, not something
  that needs to share a transaction with anything else the service does.

Where future code should go
----------------------------
A fifth analysis type gets its own repository class here, following the
same shape as the four below.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import GitHubAnalysis, LinkedInAnalysis, ResumeAnalysis, SkillGapResult


class ResumeReportRepository:
    """Database access for `ResumeAnalysis` report rows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        filename: str,
        input_data: dict[str, Any],
        ats_score: float,
        breakdown_json: dict[str, Any],
    ) -> ResumeAnalysis:
        report = ResumeAnalysis(
            user_id=user_id,
            analysis_type="resume",
            filename=filename,
            input_data=input_data,
            ats_score=ats_score,
            breakdown_json=breakdown_json,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report


class GitHubReportRepository:
    """Database access for `GitHubAnalysis` report rows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        username: str,
        input_data: dict[str, Any],
        score: float,
        breakdown_json: dict[str, Any],
    ) -> GitHubAnalysis:
        report = GitHubAnalysis(
            user_id=user_id,
            analysis_type="github",
            username=username,
            input_data=input_data,
            score=score,
            breakdown_json=breakdown_json,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report


class LinkedInReportRepository:
    """Database access for `LinkedInAnalysis` report rows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        input_data: dict[str, Any],
        score: float,
        breakdown_json: dict[str, Any],
    ) -> LinkedInAnalysis:
        report = LinkedInAnalysis(
            user_id=user_id,
            analysis_type="linkedin",
            input_data=input_data,
            score=score,
            breakdown_json=breakdown_json,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report


class SkillGapReportRepository:
    """Database access for `SkillGapResult` report rows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        target_role: str,
        input_data: dict[str, Any],
        score: float,
        matched_skills: list[str],
        missing_skills: list[str],
    ) -> SkillGapResult:
        report = SkillGapResult(
            user_id=user_id,
            analysis_type="skill_gap",
            target_role=target_role,
            input_data=input_data,
            score=score,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report
