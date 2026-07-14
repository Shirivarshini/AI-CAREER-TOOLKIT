"""
Skill-Gap Advisor — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: validates the request body via
`SkillGapAnalyzeRequest`, delegates all real work to `SkillGapService`,
and wraps the result in the standard `SuccessResponse` envelope. No
taxonomy lookup, matching, or diff logic lives here — that belongs in the
repository/service/engine layers.

Endpoint
--------
POST /skills/gap
  - Accepts a JSON body: resume-extracted skills, optional GitHub-derived
    skills, and a target role.
  - Returns matched skills, missing skills split into must-have /
    nice-to-have (each with a suggested learning resource), and an
    overall match percentage — per the task's "Return: Matched Skills,
    Missing Skills, Must Have, Nice To Have, Learning Resources"
    requirement.

Note on path prefix: this router is mounted at `/skills` under the
existing versioned API (`/api/v1`), so the full path is
`/api/v1/skills/gap`. The PRD lists this endpoint as `/api/skills/gap`;
the `/v1` segment is our existing versioning convention layered on top of
the same route — extensible, not conflicting (see `app/api/v1/resume.py`
and `app/api/v1/github.py` for the same note on earlier modules).

Where future code should go
----------------------------
Additional skill endpoints (e.g. a future roles-listing endpoint to power
a frontend dropdown) get their own `@router` function in this file.
"""

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_optional_current_user
from app.models.user import User
from app.schemas.skill_gap import SkillGapAnalysisResponse, SkillGapAnalyzeRequest
from app.services.skill_gap_service import SkillGapService, get_skill_gap_service
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Skill-Gap Advisor"])


@router.post(
    "/gap",
    response_model=SuccessResponse[SkillGapAnalysisResponse],
    summary="Compare a candidate's skills against a target role's skill taxonomy",
    description=(
        "Given resume-extracted skills, optional GitHub-derived skills, and a target role, "
        "compares the candidate's combined skill set against a predefined per-role skill "
        "taxonomy and returns matched skills, missing must-have and nice-to-have skills "
        "(each with a suggested learning resource), and an overall match percentage."
    ),
)
async def analyze_skill_gap(
    request: SkillGapAnalyzeRequest,
    current_user: User | None = Depends(get_optional_current_user),
    service: SkillGapService = Depends(get_skill_gap_service),
) -> SuccessResponse[SkillGapAnalysisResponse]:
    result = await service.analyze(request, user_id=current_user.id if current_user else None)
    return SuccessResponse(message="Skill gap analyzed successfully.", data=result)
