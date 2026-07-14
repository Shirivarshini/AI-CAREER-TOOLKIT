"""
Skill-Gap Engine package.

Framework- and storage-agnostic, mirroring `app.services.ats_scoring` and
`app.services.github_analysis`: no dependency on FastAPI, Pydantic
request/response models, HTTP, or any particular taxonomy storage. It
takes a `SkillGapContext` (candidate skills) + a `RoleTaxonomy` (already
fetched by `SkillTaxonomyRepository`) in, and returns a plain
`SkillGapAnalysisResult` out — reusable outside the API (script, CLI,
background job), not just from `SkillGapService`.

Modules:
    config.py     - SkillGapConfig (skill-alias normalization map, tunables)
    types.py       - LearningResource / SkillRequirement / RoleTaxonomy /
                       SkillGapContext / MatchedSkill / MissingSkill / SkillGapAnalysisResult
    analyzer.py    - SkillGapAnalyzer, the public entrypoint class
"""

from app.services.skill_gap.analyzer import SkillGapAnalyzer
from app.services.skill_gap.config import SkillGapConfig
from app.services.skill_gap.types import (
    LearningResource,
    MatchedSkill,
    MissingSkill,
    RoleTaxonomy,
    SkillGapAnalysisResult,
    SkillGapContext,
    SkillRequirement,
)

__all__ = [
    "SkillGapAnalyzer",
    "SkillGapConfig",
    "LearningResource",
    "MatchedSkill",
    "MissingSkill",
    "RoleTaxonomy",
    "SkillGapAnalysisResult",
    "SkillGapContext",
    "SkillRequirement",
]
