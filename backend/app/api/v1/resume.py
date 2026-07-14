"""
Resume Analyzer — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: parses the incoming multipart upload (+ optional
job description), delegates all real work to `ResumeService`, and wraps
the result in the standard `SuccessResponse` envelope. No validation,
parsing, extraction, or scoring logic lives here — that belongs in the
service/utils/repository/ats_scoring layers.

Endpoint
--------
POST /resume/analyze
  - Accepts a single multipart file upload (`file`), PDF or DOCX.
  - Accepts an optional `job_description` form field. When provided, the
    Keyword Match category compares the resume against it and returns
    `missing_keywords`, per PRD 5.1. When omitted, Keyword Match falls
    back to scoring Skills-section richness.
  - Returns extracted text, metadata, and the full ATS score (overall
    score, per-category breakdown, suggestions, missing sections).

Note on path prefix: this router is mounted at `/resume` under the
existing versioned API (`/api/v1`, established in Module 1), so the full
path is `/api/v1/resume/analyze`. The PRD lists this endpoint as
`/api/resume/analyze`; the `/v1` segment is our existing versioning
convention layered on top of the same route — extensible, not conflicting.

Where future code should go
----------------------------
Additional resume endpoints from the PRD's API spec (e.g.
`POST /resume/match-jd`) get their own `@router` function in this file.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_optional_current_user
from app.models.user import User
from app.schemas.resume import ResumeAnalysisResponse
from app.services.resume_service import ResumeService, get_resume_service
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Resume Analyzer"])


@router.post(
    "/analyze",
    response_model=SuccessResponse[ResumeAnalysisResponse],
    summary="Upload a resume, extract its text, and get an ATS score",
    description=(
        "Accepts a PDF or DOCX resume (max 5MB), validates it, extracts its "
        "plain text, scores it against ATS criteria (Keyword Match, Formatting, "
        "Section Completeness, Achievements, Parseability), and returns the "
        "extracted text alongside the score. Optionally accepts a pasted job "
        "description for a precise keyword-match comparison."
    ),
)
async def analyze_resume(
    file: UploadFile = File(..., description="Resume file (.pdf or .docx, max 5MB)"),
    job_description: str | None = Form(
        None,
        description="Optional job description text to compare resume keywords against.",
    ),
    current_user: User | None = Depends(get_optional_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> SuccessResponse[ResumeAnalysisResponse]:
    result = await service.analyze_resume(
        file, job_description=job_description, user_id=current_user.id if current_user else None
    )
    return SuccessResponse(message="Resume analyzed successfully.", data=result)
