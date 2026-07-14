"""
LinkedIn Analysis Engine package.

Framework-agnostic, mirroring `app.services.ats_scoring` and
`app.services.github_analysis`: no dependency on FastAPI, Pydantic
request/response models, HTTP, or the database. It takes an already-gathered
`LinkedInProfileContext` + config in, and returns a plain-dataclass
`LinkedInScoringResult` out — reusable outside the API (script, CLI,
background job), not just from `LinkedInService`.

Modules:
    config.py               - LinkedInAnalysisWeights / LinkedInAnalysisConfig (all tunables)
    types.py                 - LinkedInCategory / LinkedInProfileContext / CategoryScoreResult / LinkedInScoringResult
    base.py                  - CategoryScorer abstract base class
    section_scorer.py        - Generic scorer wrapping one linkedin_heuristics function
    completeness_scorer.py   - Profile Completeness / Featured / Recommendations
    insights.py               - profile_strength label, keyword suggestions, recruiter tips, next steps
    scorer.py                 - LinkedInProfileScorer, the public entrypoint class
"""

from app.services.linkedin_analysis.config import LinkedInAnalysisConfig, LinkedInAnalysisWeights
from app.services.linkedin_analysis.scorer import LinkedInProfileScorer, build_linkedin_config_from_settings
from app.services.linkedin_analysis.types import (
    CategoryScoreResult,
    LinkedInCategory,
    LinkedInProfileContext,
    LinkedInScoringResult,
)

__all__ = [
    "LinkedInProfileScorer",
    "LinkedInAnalysisConfig",
    "LinkedInAnalysisWeights",
    "LinkedInCategory",
    "LinkedInProfileContext",
    "LinkedInScoringResult",
    "CategoryScoreResult",
    "build_linkedin_config_from_settings",
]
