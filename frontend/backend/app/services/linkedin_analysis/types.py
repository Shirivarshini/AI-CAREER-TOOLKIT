"""
LinkedIn Analysis Engine — internal domain types.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.types` / `app.services.github_analysis.types`:
the scoring engine is reusable outside of FastAPI, so its inputs/outputs are
plain `dataclasses`, not Pydantic API schemas. `LinkedInService` maps
`LinkedInScoringResult` (defined here) onto `app.schemas.linkedin`'s Pydantic
response — the engine itself never imports Pydantic or FastAPI.

How it works
------------
- `LinkedInProfileContext` is the single input to the engine: the raw text of
  every profile section the PRD asks this module to analyze, already
  extracted by `LinkedInService` regardless of input method (pasted JSON or
  parsed PDF export) — category scorers never know or care which one it was.
- `RawSignalScore` / `CategoryScoreResult` follow the exact same weighting
  pattern as the ATS/GitHub engines' equivalents.
- `LinkedInScoringResult` is deliberately richer than the ATS/GitHub engines'
  result types: per the task's required response shape, it carries not just
  `overall_score`/`breakdown`/suggestions but also `missing_sections`,
  per-section `rewrite_suggestions`, `keyword_suggestions`, `recruiter_tips`,
  a human-readable `profile_strength` label, and prioritized `next_steps` —
  everything `LinkedInService` needs to build the API response with no
  further scoring logic of its own.

Where future code should go
----------------------------
A new scoring category needs a new `CategoryScorer` subclass producing a
`RawSignalScore` — this file only changes if a category needs a genuinely
new output shape beyond score/suggestions/details, or if the final response
needs a new top-level field.
"""

from dataclasses import dataclass, field
from enum import Enum


class LinkedInCategory(str, Enum):
    """The eight LinkedIn profile scoring categories that make up the overall score."""

    HEADLINE = "headline"
    ABOUT = "about"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    EDUCATION = "education"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    COMPLETENESS = "completeness"


# The seven content categories a real profile section maps to — every
# `LinkedInCategory` except `COMPLETENESS`, which is a derived, engine-level
# meta-category (profile completeness + Featured + Recommendations) rather
# than a single pasted/parsed section. Used to decide which categories can
# ever be "missing" and which get a per-section rewrite suggestion.
CONTENT_CATEGORIES: tuple[LinkedInCategory, ...] = (
    LinkedInCategory.HEADLINE,
    LinkedInCategory.ABOUT,
    LinkedInCategory.EXPERIENCE,
    LinkedInCategory.SKILLS,
    LinkedInCategory.EDUCATION,
    LinkedInCategory.PROJECTS,
    LinkedInCategory.CERTIFICATIONS,
)


@dataclass(frozen=True)
class LinkedInProfileContext:
    """
    Everything a category scorer might need to compute its score.

    Every field is the raw text for one profile section (or `None` if that
    section is absent), already normalized by `LinkedInService` from either
    input method. `featured` and `recommendations` back the Completeness
    category's Featured-section and Recommendations-section signals (PRD's
    "Analyze" list); `target_role` is accepted now but not yet consumed by
    any scorer — see `insights.py`'s "Where future code should go" note for
    how it plugs into keyword suggestions once the Skill-Gap module's role
    taxonomy is wired in.
    """

    headline: str | None = None
    about: str | None = None
    experience: str | None = None
    education: str | None = None
    skills: str | None = None
    certifications: str | None = None
    projects: str | None = None
    featured: str | None = None
    recommendations: str | None = None
    target_role: str | None = None


@dataclass(frozen=True)
class RawSignalScore:
    """
    A single category scorer's output, before the engine applies weighting.

    `score` must be in the 0–100 range. `details` is a free-form bag for
    category-specific structured data the engine needs afterward — every
    content-category scorer sets `details["present"]` so `LinkedInProfileScorer`
    knows whether that section was missing, without re-inspecting raw text.
    """

    score: float
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CategoryScoreResult:
    """A `RawSignalScore` combined with the weight the engine applied to it."""

    category: LinkedInCategory
    score: float
    weight: float
    present: bool
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkedInScoringResult:
    """The LinkedIn Analysis Engine's final output for a single profile."""

    overall_score: float
    breakdown: dict[LinkedInCategory, CategoryScoreResult]
    missing_sections: list[LinkedInCategory]
    rewrite_suggestions: dict[LinkedInCategory, list[str]]
    keyword_suggestions: list[str]
    recruiter_tips: list[str]
    profile_strength: str
    next_steps: list[str]
