"""
LinkedIn Optimizer — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the LinkedIn Optimizer feature, separate
from the generic `app/schemas/common.py`, following the same pattern as
`app/schemas/resume.py`, `app/schemas/github.py`, and `app/schemas/skill_gap.py`.

Per the PRD (section 6.3 / 15): LinkedIn is never scraped — content is
either pasted directly (`LinkedInProfileInput`, used for the
`application/json` request path) or comes from parsing an uploaded
LinkedIn PDF export (the `multipart/form-data` request path — see
`app/api/v1/linkedin.py` for how the router picks between the two).
Both paths converge on the same internal section representation, so a
single set of response schemas serves either input method.

This is "Part 2" of the module: on top of Part 1's per-section presence,
preliminary per-section score, and section-specific suggestions,
`LinkedInAnalysisResponse` now also carries a weighted `overall_score`, a
per-category `breakdown` (via `app.services.linkedin_analysis.LinkedInProfileScorer`),
`rewrite_suggestions`, `keyword_suggestions`, `recruiter_tips`, a
`profile_strength` label, and prioritized `next_steps` — see
`app/services/linkedin_analysis/` for the scoring engine that produces them,
and `app/services/linkedin_service.py` for how it maps onto this schema.

Where future code should go
----------------------------
Additional analyzed inputs (e.g. a target role, once keyword suggestions
are role-aware — see `app.services.linkedin_analysis.insights`'s docstring)
belong as new optional fields on `LinkedInProfileInput`.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

# LinkedIn's own published limits — used both to bound request payloads
# and as a signal inside the heuristics (see app/utils/linkedin_heuristics.py)
# for "did they use the space available".
_HEADLINE_MAX_LENGTH = 220
_ABOUT_MAX_LENGTH = 2600
_EXPERIENCE_MAX_LENGTH = 10_000
_EDUCATION_MAX_LENGTH = 5_000
_SKILLS_MAX_LENGTH = 3_000
_CERTIFICATIONS_MAX_LENGTH = 3_000
_PROJECTS_MAX_LENGTH = 5_000
_FEATURED_MAX_LENGTH = 5_000
_RECOMMENDATIONS_MAX_LENGTH = 5_000


class LinkedInInputMethod(str, Enum):
    """Which of the PRD's two supported input methods produced this analysis."""

    JSON = "json"
    PDF = "pdf"


class LinkedInSectionName(str, Enum):
    """The seven profile sections analyzed by this module."""

    HEADLINE = "headline"
    ABOUT = "about"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    PROJECTS = "projects"


class LinkedInProfileInput(BaseModel):
    """
    Request body for POST /linkedin/analyze when submitted as
    `application/json` — manually pasted LinkedIn profile content, per PRD
    6.3 ("the user pastes profile content ... into a form").

    Every field is individually optional — a real profile may genuinely be
    missing a section (e.g. no Certifications) and that itself is a
    detected finding (see `LinkedInAnalysisResponse.missing_sections`), not
    a validation failure. At least one field must be non-empty, or there
    is nothing to analyze at all — enforced by
    `_require_at_least_one_section`, the same pattern used by
    `SkillGapAnalyzeRequest` in `app/schemas/skill_gap.py`.
    """

    headline: str | None = Field(
        None,
        max_length=_HEADLINE_MAX_LENGTH,
        description="LinkedIn headline (LinkedIn's own limit is 220 characters).",
        examples=["Backend Engineer | Python, FastAPI, PostgreSQL"],
    )
    about: str | None = Field(
        None,
        max_length=_ABOUT_MAX_LENGTH,
        description="The 'About'/Summary section (LinkedIn's own limit is ~2,600 characters).",
    )
    experience: str | None = Field(
        None,
        max_length=_EXPERIENCE_MAX_LENGTH,
        description="Pasted Experience section — all roles and bullet points.",
    )
    education: str | None = Field(
        None, max_length=_EDUCATION_MAX_LENGTH, description="Pasted Education section."
    )
    skills: str | None = Field(
        None,
        max_length=_SKILLS_MAX_LENGTH,
        description="Pasted Skills section (comma-, pipe-, or line-separated).",
        examples=["Python, FastAPI, PostgreSQL, Docker, System Design"],
    )
    certifications: str | None = Field(
        None,
        max_length=_CERTIFICATIONS_MAX_LENGTH,
        description="Pasted Licenses & Certifications section.",
    )
    projects: str | None = Field(
        None, max_length=_PROJECTS_MAX_LENGTH, description="Pasted Projects section."
    )
    featured: str | None = Field(
        None,
        max_length=_FEATURED_MAX_LENGTH,
        description="Pasted Featured section (links/posts/media the user chose to highlight).",
    )
    recommendations: str | None = Field(
        None,
        max_length=_RECOMMENDATIONS_MAX_LENGTH,
        description=(
            "Pasted Recommendations received, one per line/comma — used only to count them, "
            "not to score their content."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _blank_strings_to_none(cls, data: object) -> object:
        """
        Normalize whitespace-only field values to None *before* field
        validation, so a section of only spaces/newlines is treated the
        same as an omitted section (both mean "missing"), consistently
        with how the PDF-parsing path represents a genuinely absent
        section.
        """
        if not isinstance(data, dict):
            return data
        cleaned = dict(data)
        for key in (
            "headline",
            "about",
            "experience",
            "education",
            "skills",
            "certifications",
            "projects",
            "featured",
            "recommendations",
        ):
            value = cleaned.get(key)
            if isinstance(value, str) and not value.strip():
                cleaned[key] = None
        return cleaned

    @model_validator(mode="after")
    def _require_at_least_one_section(self) -> "LinkedInProfileInput":
        if not any(
            [
                self.headline,
                self.about,
                self.experience,
                self.education,
                self.skills,
                self.certifications,
                self.projects,
            ]
        ):
            raise ValueError(
                "Provide at least one LinkedIn profile section (headline, about, "
                "experience, education, skills, certifications, or projects) to analyze."
            )
        return self


class LinkedInSectionResult(BaseModel):
    """Preliminary (per-section, not overall) analysis result for one profile section."""

    content: str | None = Field(
        None, description="The parsed/pasted content used for this section, or null if missing."
    )
    present: bool = Field(..., description="Whether this section had any content to analyze.")
    score: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Preliminary heuristic score for this section, 0-100. Null if the section is missing.",
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Actionable, section-specific rewrite suggestions."
    )


class LinkedInScoreCategoryResult(BaseModel):
    """A single LinkedIn scoring category's result (e.g. Headline, Completeness)."""

    score: float = Field(..., ge=0, le=100, description="Category score, 0-100.")
    weight: float = Field(..., ge=0, le=1, description="This category's weight in the overall score.")
    suggestions: list[str] = Field(default_factory=list, description="Actionable fixes for this category.")


class LinkedInScoreBreakdown(BaseModel):
    """Per-category breakdown of the overall profile score, per the task's required response shape."""

    headline: LinkedInScoreCategoryResult
    about: LinkedInScoreCategoryResult
    experience: LinkedInScoreCategoryResult
    skills: LinkedInScoreCategoryResult
    education: LinkedInScoreCategoryResult
    projects: LinkedInScoreCategoryResult
    certifications: LinkedInScoreCategoryResult
    completeness: LinkedInScoreCategoryResult = Field(
        ...,
        description="Profile completeness: core-section presence, Featured section, and Recommendations.",
    )


class LinkedInAnalysisResponse(BaseModel):
    """
    Response returned by POST /linkedin/analyze.

    Combines Part 1's per-section results (`sections`, `missing_sections`,
    `input_method`) with Part 2's weighted scoring-engine output:
    `overall_score` and `breakdown` come from
    `app.services.linkedin_analysis.LinkedInProfileScorer`, and
    `rewrite_suggestions` / `keyword_suggestions` / `recruiter_tips` /
    `profile_strength` / `next_steps` are that engine's higher-level,
    actionable output — see `app/services/linkedin_analysis/` for how each
    is computed and `app/services/linkedin_service.py` for the mapping.
    """

    input_method: LinkedInInputMethod = Field(
        ..., description="Whether this analysis came from a pasted JSON body or an uploaded PDF export."
    )
    sections: dict[LinkedInSectionName, LinkedInSectionResult] = Field(
        ..., description="Per-section parsed content, presence, preliminary score, and suggestions."
    )
    missing_sections: list[LinkedInSectionName] = Field(
        ..., description="Sections that had no content to analyze, in section order."
    )
    overall_score: float = Field(..., ge=0, le=100, description="Weighted overall profile score, 0-100.")
    breakdown: LinkedInScoreBreakdown = Field(..., description="Per-category weighted score breakdown.")
    rewrite_suggestions: dict[LinkedInSectionName, list[str]] = Field(
        ..., description="Section-specific rewrite suggestions, keyed by section."
    )
    keyword_suggestions: list[str] = Field(
        default_factory=list,
        description="High-value recruiter-search keywords not found in the headline, about, or skills sections.",
    )
    recruiter_tips: list[str] = Field(
        default_factory=list, description="General, profile-wide recruiter-visibility tips."
    )
    profile_strength: str = Field(
        ..., description="Human-readable label for the overall score (e.g. 'Excellent', 'Needs Improvement')."
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="A single prioritized action list: missing sections first, then the lowest-scoring "
        "present categories' top suggestion.",
    )
