"""
LinkedIn Optimizer — API router.

Why this file exists
---------------------
Thin HTTP adapter layer: figures out which of the PRD's two supported
input methods a request used, delegates all real work to
`LinkedInService`, and wraps the result in the standard `SuccessResponse`
envelope. No validation, parsing, or scoring logic lives here.

Endpoint
--------
POST /linkedin/analyze
  - Accepts EITHER:
      (a) `Content-Type: application/json` — a `LinkedInProfileInput` body
          of manually pasted profile sections, per PRD 5.3 ("User can
          paste profile sections manually"), OR
      (b) `Content-Type: multipart/form-data` — a single `file` field
          containing a LinkedIn PDF export (.pdf, max 5MB), per PRD 5.3
          ("...or upload a LinkedIn PDF export").
  - Returns parsed sections, detected missing sections, per-section
    scores/suggestions, a weighted overall profile score and category
    breakdown, keyword suggestions, recruiter tips, a profile-strength
    label, and prioritized next steps (see `app/schemas/linkedin.py` and
    `app/services/linkedin_analysis/`).

Why a raw `Request` instead of two separate routes
----------------------------------------------------
The task specifies one endpoint, `POST /api/linkedin/analyze`, accepting
either input method. FastAPI resolves a route's expected body shape from
its declared parameters at import time — a function can't declare both a
Pydantic JSON body parameter and `File(...)`/`Form(...)` parameters
together, since the latter forces the whole request to be parsed as
multipart/form-data. Reading `request` directly and branching on the
`Content-Type` header (see `analyze_linkedin_profile` below) is the
standard way to genuinely support two request-body shapes on one route.
The `openapi_extra` on the route decorator below documents both shapes
for Swagger UI (see "How to test in Swagger" at the bottom of this file).

Note on path prefix: this router is mounted at `/linkedin` under the
existing versioned API (`/api/v1`, established in Module 1), so the full
path is `/api/v1/linkedin/analyze`. The PRD lists this endpoint as
`/api/linkedin/analyze`; the `/v1` segment is our existing versioning
convention layered on top of the same route — extensible, not conflicting
(see the same note in `resume.py` / `github.py`).

How to test in Swagger
-----------------------
Open `/docs`, expand `POST /api/v1/linkedin/analyze`, click "Try it out".
Swagger UI shows a "Request body" content-type dropdown (because
`openapi_extra` below declares both media types):
  - Select `application/json` to test pasted-content analysis. Fill in
    any subset of the seven fields (at least one) and execute.
  - Select `multipart/form-data` to test the PDF path. A file picker for
    the `file` field appears — attach a `.pdf` and execute.
Both paths return the same `LinkedInAnalysisResponse` shape.

Where future code should go
----------------------------
Additional LinkedIn endpoints from the PRD's API spec get their own
`@router` function in this file.
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_optional_current_user
from app.core.exceptions import UnsupportedFileTypeError
from app.models.user import User
from app.schemas.linkedin import LinkedInAnalysisResponse, LinkedInProfileInput
from app.services.linkedin_service import LinkedInService, get_linkedin_service
from app.utils.response import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LinkedIn Optimizer"])

# Documents both accepted request-body shapes for Swagger UI / OpenAPI
# clients, since `analyze_linkedin_profile` below intentionally declares no
# FastAPI-bound body parameter (see the module docstring for why). The JSON
# schema is inlined directly (via `model_json_schema()`) rather than a
# `$ref` into `components/schemas`, since `LinkedInProfileInput` is never
# used as a bound parameter and so is never auto-registered there.
_ANALYZE_REQUEST_BODY_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": LinkedInProfileInput.model_json_schema(),
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "LinkedIn PDF export (.pdf, max 5MB).",
                        }
                    },
                    "required": ["file"],
                }
            },
        },
    }
}


@router.post(
    "/analyze",
    response_model=SuccessResponse[LinkedInAnalysisResponse],
    summary="Analyze a LinkedIn profile from pasted content or a PDF export",
    description=(
        "Accepts EITHER a JSON body of manually pasted profile sections "
        "(headline, about, experience, education, skills, certifications, projects) "
        "OR a multipart upload of a LinkedIn 'Save to PDF' profile export (max 5MB). "
        "LinkedIn is never scraped. Runs rule-based (heuristic-only) analysis per "
        "section and returns parsed sections, missing sections, per-section scores "
        "and rewrite suggestions, a weighted overall profile score with a "
        "per-category breakdown, keyword suggestions, recruiter tips, a "
        "profile-strength label, and prioritized next steps."
    ),
    openapi_extra=_ANALYZE_REQUEST_BODY_SCHEMA,
)
async def analyze_linkedin_profile(
    request: Request,
    current_user: User | None = Depends(get_optional_current_user),
    service: LinkedInService = Depends(get_linkedin_service),
) -> SuccessResponse[LinkedInAnalysisResponse]:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    logger.info("LinkedIn analyze request received (content-type='%s')", content_type or "missing")
    user_id = current_user.id if current_user else None

    if content_type == "application/json":
        raw_body = await request.json()
        payload = service.parse_json_payload(raw_body)
        result = await service.analyze_from_json(payload, user_id=user_id)
    elif content_type == "multipart/form-data":
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "filename"):
            raise UnsupportedFileTypeError(
                "No 'file' field found in the multipart upload. Attach a LinkedIn "
                "PDF export under a form field named 'file'."
            )
        result = await service.analyze_from_pdf(upload, user_id=user_id)
    else:
        raise UnsupportedFileTypeError(
            f"Unsupported Content-Type '{content_type or 'missing'}'. Send either "
            "'application/json' (pasted profile content) or 'multipart/form-data' "
            "(a LinkedIn PDF export)."
        )

    return SuccessResponse(message="LinkedIn profile analyzed successfully.", data=result)
