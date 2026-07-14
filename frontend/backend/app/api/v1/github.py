"""
GitHub Profile Analysis — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: validates the request body via
`GitHubAnalyzeRequest`, delegates all real work to
`GitHubAnalysisService`, and wraps the result in the standard
`SuccessResponse` envelope. No HTTP-calling, scoring, or caching logic
lives here — that belongs in the client/service/scoring-engine layers.

Endpoint
--------
POST /github/analyze
  - Accepts a JSON body: `{"username": "<github-username>"}`.
  - Returns profile statistics, the engagement-ranked top repositories,
    and the full profile score (overall score, per-category breakdown,
    suggestions) — per the task's "Return: Profile Score, Statistics,
    Suggestions" requirement.

Note on path prefix: this router is mounted at `/github` under the
existing versioned API (`/api/v1`, established in Module 1), so the full
path is `/api/v1/github/analyze`. The PRD lists this endpoint as
`/api/github/analyze`; the `/v1` segment is our existing versioning
convention layered on top of the same route — extensible, not conflicting
(see `app/api/v1/resume.py` for the same note on Module 2).

Where future code should go
----------------------------
Additional GitHub endpoints get their own `@router` function in this file.
"""

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_optional_current_user
from app.models.user import User
from app.schemas.github import GitHubAnalysisResponse, GitHubAnalyzeRequest
from app.services.github_service import GitHubAnalysisService, get_github_analysis_service
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GitHub Analysis"])


@router.post(
    "/analyze",
    response_model=SuccessResponse[GitHubAnalysisResponse],
    summary="Analyze a GitHub profile and get a profile strength score",
    description=(
        "Given a GitHub username, pulls public profile data via the GitHub REST API "
        "(repositories, stars, forks, languages, top/'pinned'-proxy repositories, README "
        "quality, and recent contribution activity) and returns a profile strength score, "
        "supporting statistics, and actionable, specific suggestions. Results are cached "
        "briefly per username to conserve GitHub's API rate limit."
    ),
)
async def analyze_github_profile(
    request: GitHubAnalyzeRequest,
    current_user: User | None = Depends(get_optional_current_user),
    service: GitHubAnalysisService = Depends(get_github_analysis_service),
) -> SuccessResponse[GitHubAnalysisResponse]:
    result = await service.analyze_profile(
        request.username, user_id=current_user.id if current_user else None
    )
    return SuccessResponse(message="GitHub profile analyzed successfully.", data=result)
