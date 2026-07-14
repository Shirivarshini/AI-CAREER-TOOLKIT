"""
Skill-Gap Advisor — service layer (taxonomy lookup -> diff -> response mapping -> report storage).

Why this file exists
---------------------
The service layer coordinates `SkillTaxonomyRepository` (taxonomy lookup)
and the framework-agnostic `SkillGapAnalyzer` engine — without either
concern's implementation details leaking into the API router. The router
stays a thin HTTP adapter; this is where the "recipe" for handling a
skill-gap request lives, matching the pattern established by
`ResumeService` and `GitHubAnalysisService`.

How it works
------------
`SkillGapService.analyze()`:
  1. Looks up the requested `target_role` in the taxonomy repository
     (case-insensitive, alias-aware — see `JSONSkillTaxonomyRepository`).
     Raises `TargetRoleNotFoundError` (with the list of available roles in
     the message) if no match — per the project's established pattern of
     "a clear message rather than a generic error" for a bad identifier
     (mirrors `GitHubUserNotFoundError` in the GitHub module).
  2. Builds a `SkillGapContext` from the request's resume/GitHub skills.
  3. Runs `SkillGapAnalyzer.analyze()` — pure, in-memory, no I/O; small
     enough not to need `asyncio.to_thread` (unlike the ATS engine's
     regex-heavy full-resume-text scoring).
  4. Maps the result onto `SkillGapAnalysisResponse`.
  5. Persists a `SkillGapResult` report row via `SkillGapReportRepository`
     (matched/missing skill names, the match percentage as `score`, and
     the request's own inputs as `input_data`). A storage failure is
     logged and swallowed, never surfacing as a failed request.
  6. Returns the response from step 4, unaffected by whether step 5
     succeeded.
"""

import logging
import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import TargetRoleNotFoundError
from app.repositories.report_repository import SkillGapReportRepository
from app.repositories.skill_taxonomy_repository import SkillTaxonomyRepository, get_skill_taxonomy_repository
from app.schemas.skill_gap import (
    MatchedSkillSchema,
    MissingSkillSchema,
    MissingSkillsBreakdown,
    SkillGapAnalyzeRequest,
    SkillGapAnalysisResponse,
)
from app.services.skill_gap import SkillGapAnalyzer, SkillGapContext
from app.services.skill_gap.types import MatchedSkill, MissingSkill, SkillGapAnalysisResult

logger = logging.getLogger(__name__)


class SkillGapService:
    """Orchestrates taxonomy lookup and skill-gap analysis for one request."""

    def __init__(
        self,
        taxonomy_repository: SkillTaxonomyRepository,
        analyzer: SkillGapAnalyzer,
        report_repository: SkillGapReportRepository,
    ) -> None:
        self._taxonomy_repository = taxonomy_repository
        self._analyzer = analyzer
        self._report_repository = report_repository

    async def analyze(
        self, request: SkillGapAnalyzeRequest, user_id: uuid.UUID | None = None
    ) -> SkillGapAnalysisResponse:
        """
        Compare the request's resume/GitHub skills against the target role's
        taxonomy and return matched skills, missing must-have/nice-to-have
        skills (each with a learning resource), and a match percentage.

        Raises TargetRoleNotFoundError if `request.target_role` doesn't
        match any known role or alias.
        """
        taxonomy = self._taxonomy_repository.get_taxonomy(request.target_role)
        if taxonomy is None:
            available = ", ".join(self._taxonomy_repository.list_roles())
            raise TargetRoleNotFoundError(
                f"No skill taxonomy found for target role '{request.target_role}'. "
                f"Available roles: {available}."
            )

        context = SkillGapContext(
            resume_skills=request.resume_skills,
            github_skills=request.github_skills,
            target_role=request.target_role,
        )
        result = self._analyzer.analyze(context, taxonomy)

        logger.info(
            "Skill-gap analysis for role '%s': %.2f%% match (%d matched, %d missing must-have)",
            result.target_role,
            result.match_percentage,
            len(result.matched_skills),
            len(result.missing_must_have),
        )

        response = self._map_to_schema(result)

        # Persist a report row for this successful analysis. Never lets a
        # storage failure surface as a failed request.
        try:
            await self._report_repository.create(
                user_id=user_id,
                target_role=result.target_role,
                input_data={
                    "target_role": request.target_role,
                    "resume_skills": request.resume_skills,
                    "github_skills": request.github_skills,
                },
                score=result.match_percentage,
                matched_skills=[s.skill for s in result.matched_skills],
                missing_skills=[s.skill for s in (result.missing_must_have + result.missing_nice_to_have)],
            )
        except Exception:
            logger.exception("Failed to save skill-gap analysis report for role '%s'", result.target_role)

        return response

    @staticmethod
    def _map_to_schema(result: SkillGapAnalysisResult) -> SkillGapAnalysisResponse:
        def _matched(skill: MatchedSkill) -> MatchedSkillSchema:
            return MatchedSkillSchema(skill=skill.skill, sources=list(skill.sources))

        def _missing(skill: MissingSkill) -> MissingSkillSchema:
            resource = (
                {"title": skill.resource.title, "url": skill.resource.url} if skill.resource else None
            )
            return MissingSkillSchema(skill=skill.skill, resource=resource)

        return SkillGapAnalysisResponse(
            target_role=result.target_role,
            matched_skills=[_matched(s) for s in result.matched_skills],
            missing_skills=MissingSkillsBreakdown(
                must_have=[_missing(s) for s in result.missing_must_have],
                nice_to_have=[_missing(s) for s in result.missing_nice_to_have],
            ),
            match_percentage=result.match_percentage,
        )


def get_skill_gap_service(db: AsyncSession = Depends(get_db)) -> SkillGapService:
    """
    FastAPI dependency factory for SkillGapService.

    The taxonomy repository is a cached singleton (see
    `get_skill_taxonomy_repository`); the analyzer is cheap enough to
    construct per request. `db` is only used to build the
    `SkillGapReportRepository` that persists each successful analysis.
    """
    return SkillGapService(
        taxonomy_repository=get_skill_taxonomy_repository(),
        analyzer=SkillGapAnalyzer(),
        report_repository=SkillGapReportRepository(db),
    )
