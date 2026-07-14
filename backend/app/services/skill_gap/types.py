"""
Skill-Gap Engine — internal domain types.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.types` / `app.services.github_analysis.
types`: the engine is reusable outside of FastAPI/storage, so its inputs
and outputs are plain `dataclasses`, not Pydantic API schemas or JSON
dicts. `SkillGapService` is responsible for fetching a `RoleTaxonomy` (via
`SkillTaxonomyRepository`) and mapping `SkillGapAnalysisResult` (defined
here) onto the Pydantic response schema — the engine itself never imports
Pydantic, FastAPI, or knows how the taxonomy was stored.

How it works
------------
- `LearningResource` / `SkillRequirement` / `RoleTaxonomy` describe one
  role's requirements — this is the engine's view of "the taxonomy",
  independent of whether it came from a JSON file (today) or a database
  (later); see `app/repositories/skill_taxonomy_repository.py`.
- `SkillGapContext` is the single input describing what the candidate
  actually has: their resume-derived skills, GitHub-derived skills
  (optional), and the requested target role label.
- `MatchedSkill` / `MissingSkill` are per-skill results; `MissingSkill`
  carries the taxonomy's suggested `LearningResource`, per the task's
  "Learning Resources" output requirement.
- `SkillGapAnalysisResult` is the engine's final output.

Where future code should go
----------------------------
If a new derived metric is needed (e.g. per-skill confidence, or a
weighted score beyond `match_percentage`), add a field to
`SkillGapAnalysisResult` and compute it in `SkillGapAnalyzer.analyze()`
— these types don't need to change otherwise.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LearningResource:
    """A single suggested resource for learning a missing skill."""

    title: str
    url: str


@dataclass(frozen=True)
class SkillRequirement:
    """One skill required (or recommended) for a role, with an optional learning resource."""

    skill: str
    resource: LearningResource | None = None


@dataclass(frozen=True)
class RoleTaxonomy:
    """A single role's full skill taxonomy: must-have and nice-to-have skills."""

    role: str
    aliases: tuple[str, ...] = ()
    must_have: tuple[SkillRequirement, ...] = ()
    nice_to_have: tuple[SkillRequirement, ...] = ()


@dataclass(frozen=True)
class SkillGapContext:
    """Everything the engine needs to compute one skill-gap analysis."""

    resume_skills: list[str] = field(default_factory=list)
    github_skills: list[str] = field(default_factory=list)
    target_role: str = ""


@dataclass(frozen=True)
class MatchedSkill:
    """A taxonomy skill the candidate already has, and where it was found."""

    skill: str
    sources: tuple[str, ...]  # e.g. ("resume",), ("github",), or ("resume", "github")


@dataclass(frozen=True)
class MissingSkill:
    """A taxonomy skill the candidate does not (yet) have, with a suggested resource."""

    skill: str
    resource: LearningResource | None = None


@dataclass(frozen=True)
class SkillGapAnalysisResult:
    """The Skill-Gap Engine's final output for one candidate x role comparison."""

    target_role: str
    matched_skills: list[MatchedSkill]
    missing_must_have: list[MissingSkill]
    missing_nice_to_have: list[MissingSkill]
    match_percentage: float  # coverage of must-have skills, 0-100 (see analyzer.py)
