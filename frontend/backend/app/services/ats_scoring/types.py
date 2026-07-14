"""
ATS Scoring Engine — internal domain types.

Why this file exists
---------------------
The scoring engine is designed to be reusable outside of FastAPI (see the
package docstring in `__init__.py`), so its inputs/outputs are plain
`dataclasses`, not Pydantic API schemas. `ResumeService` is responsible for
mapping `ATSScoringResult` (defined here) onto the Pydantic
`ATSScoringResultSchema` (defined in `app/schemas/resume.py`) for the HTTP
response — the engine itself never imports Pydantic or FastAPI.

How it works
------------
- `ATSScoringContext` is the single input to the engine: the resume text
  plus everything a category scorer might need (file metadata, optional
  job description).
- `RawCategoryScore` is what each individual `CategoryScorer` returns —
  just a 0–100 score, suggestions, and free-form details. It does NOT know
  its own weight; weighting is the engine's job, not the scorer's.
- `CategoryScoreResult` is `RawCategoryScore` + the weight that was applied
  to it, produced by the engine after it looks up the configured weight
  for that category.
- `ATSScoringResult` is the engine's final output: overall score, full
  breakdown, aggregated suggestions, missing sections, missing keywords.

Where future code should go
----------------------------
If a new category is added later, it needs a new `RawCategoryScore`
producer (a new `CategoryScorer` subclass) — no changes needed here unless
the category needs genuinely new output shape beyond score/suggestions/details.
"""

from dataclasses import dataclass, field
from enum import Enum


class ATSCategory(str, Enum):
    """The five ATS scoring categories, per the PRD (section 6.1)."""

    KEYWORD_MATCH = "keyword_match"
    FORMATTING = "formatting"
    SECTION_COMPLETENESS = "section_completeness"
    ACHIEVEMENTS = "achievements"
    PARSEABILITY = "parseability"


@dataclass(frozen=True)
class ATSScoringContext:
    """Everything a category scorer might need to compute its score."""

    resume_text: str
    file_extension: str  # ".pdf" or ".docx"
    file_size_bytes: int
    job_description: str | None = None


@dataclass(frozen=True)
class RawCategoryScore:
    """
    A single category scorer's output, before the engine applies weighting.

    `score` must be in the 0–100 range. `details` is a free-form bag for
    category-specific structured data the engine may want to surface at
    the top level (e.g. `missing_sections`, `missing_keywords`).
    """

    score: float
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CategoryScoreResult:
    """A `RawCategoryScore` combined with the weight the engine applied to it."""

    category: ATSCategory
    score: float
    weight: float
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ATSScoringResult:
    """The ATS Scoring Engine's final output for a single resume."""

    overall_score: float
    breakdown: dict[ATSCategory, CategoryScoreResult]
    suggestions: list[str]
    missing_sections: list[str]
    missing_keywords: list[str]
