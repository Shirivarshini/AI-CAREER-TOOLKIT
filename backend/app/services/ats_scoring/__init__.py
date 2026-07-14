"""
ATS Scoring Engine package.

This package is intentionally framework-agnostic: it has no dependency on
FastAPI, Pydantic request/response models, or the database. It takes plain
text + config in, and returns plain dataclasses out. This means it can be
reused outside the API — a batch script, a CLI, a background job — not
just from `ResumeService`.

Modules:
    config.py           - ATSScoringWeights / ATSScoringConfig (all tunables)
    section_parser.py   - splits resume text into named sections
    types.py             - RawCategoryScore / CategoryScoreResult / ATSScoringContext / ATSScoringResult
    base.py               - CategoryScorer abstract base class
    keyword_match_scorer.py
    formatting_scorer.py
    section_completeness_scorer.py
    achievements_scorer.py
    parseability_scorer.py
    scorer.py             - ATSScorer, the public entrypoint class
"""

from app.services.ats_scoring.config import ATSScoringConfig, ATSScoringWeights
from app.services.ats_scoring.scorer import ATSScorer, build_ats_config_from_settings
from app.services.ats_scoring.types import ATSScoringContext, ATSScoringResult

__all__ = [
    "ATSScorer",
    "ATSScoringConfig",
    "ATSScoringWeights",
    "ATSScoringContext",
    "ATSScoringResult",
    "build_ats_config_from_settings",
]
