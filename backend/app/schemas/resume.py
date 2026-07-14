"""
Resume Analyzer — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the Resume Analyzer feature live here,
separate from the generic `app/schemas/common.py`.

Module 2 added file metadata + raw extracted text. Module 3 (this update)
adds the ATS scoring result as an additional field on the same response —
per the PRD's API spec, `POST /resume/analyze` returns "upload + ATS
score" as a single call, so scoring fields are appended to the existing
schema rather than introducing a parallel response type.

Where future code should go
----------------------------
Future resume endpoints from the PRD's API spec (e.g.
`POST /resume/match-jd`) get their own schemas here, reusing
`ATSScoreCategoryResult` / `ATSScoreBreakdown` where their shape overlaps.
"""

from enum import Enum

from pydantic import BaseModel, Field


class ResumeFileType(str, Enum):
    """Supported resume file types."""

    PDF = "pdf"
    DOCX = "docx"


class ATSScoreCategoryResult(BaseModel):
    """A single ATS scoring category's result (e.g. Keyword Match, Formatting)."""

    score: float = Field(..., ge=0, le=100, description="Category score, 0-100.")
    weight: float = Field(..., ge=0, le=1, description="This category's weight in the overall score.")
    suggestions: list[str] = Field(
        default_factory=list, description="Actionable fixes specific to this category."
    )


class ATSScoreBreakdown(BaseModel):
    """Per-category breakdown of the overall ATS score, per PRD section 6.1."""

    keyword_match: ATSScoreCategoryResult
    formatting: ATSScoreCategoryResult
    section_completeness: ATSScoreCategoryResult
    achievements: ATSScoreCategoryResult
    parseability: ATSScoreCategoryResult


class ATSScoringResultSchema(BaseModel):
    """The full ATS scoring result for one resume."""

    overall_score: float = Field(..., ge=0, le=100, description="Weighted overall ATS score, 0-100.")
    breakdown: ATSScoreBreakdown = Field(..., description="Per-category scores and suggestions.")
    suggestions: list[str] = Field(
        ..., description="All actionable fixes across categories, deduplicated."
    )
    missing_sections: list[str] = Field(
        ..., description="Expected resume sections that were not detected."
    )
    missing_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Keywords present in the job description but missing from the resume. "
            "Only populated when a job description was provided."
        ),
    )


class ResumeAnalysisResponse(BaseModel):
    """Response returned by POST /resume/analyze: extracted text + ATS score."""

    filename: str = Field(..., description="Original uploaded filename.")
    file_type: ResumeFileType = Field(..., description="Detected resume file type.")
    size_bytes: int = Field(..., description="Size of the uploaded file, in bytes.")
    character_count: int = Field(..., description="Number of characters in the extracted text.")
    word_count: int = Field(..., description="Number of whitespace-separated words extracted.")
    extracted_text: str = Field(..., description="Raw text extracted from the resume.")
    ats_score: ATSScoringResultSchema = Field(..., description="ATS scoring result for this resume.")
