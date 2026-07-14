"""
Skill-Gap Advisor — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the Skill-Gap Advisor feature, separate
from the generic `app/schemas/common.py`, following the same pattern as
`app/schemas/resume.py` and `app/schemas/github.py`.

Where future code should go
----------------------------
Future skill-gap endpoints from the PRD's API spec get their own schemas
here, reusing `LearningResourceSchema` / `MissingSkillSchema` where their
shape overlaps.
"""

from pydantic import BaseModel, Field, model_validator


class SkillGapAnalyzeRequest(BaseModel):
    """
    Request body for POST /skills/gap.

    Per PRD 5.4 ("Skill-gap can run using resume data alone if GitHub/
    LinkedIn data isn't provided"), `github_skills` is optional and
    defaults to empty — but at least one of `resume_skills` /
    `github_skills` must be non-empty, or there's nothing to compare.
    """

    resume_skills: list[str] = Field(
        default_factory=list,
        description="Skills extracted from the candidate's resume (e.g. from the Resume Analyzer's Skills section).",
        examples=[["Python", "SQL", "Docker", "Git"]],
    )
    github_skills: list[str] = Field(
        default_factory=list,
        description="Skills inferred from the candidate's GitHub activity (e.g. the GitHub Analysis module's language distribution).",
        examples=[["Python", "JavaScript"]],
    )
    target_role: str = Field(
        ...,
        min_length=1,
        description="The role to compare skills against (dropdown selection or free text).",
        examples=["Backend Developer"],
    )

    @model_validator(mode="after")
    def _require_at_least_one_skill_source(self) -> "SkillGapAnalyzeRequest":
        if not self.resume_skills and not self.github_skills:
            raise ValueError(
                "At least one of resume_skills or github_skills must be provided — "
                "there's nothing to compare against the target role's taxonomy otherwise."
            )
        return self


class LearningResourceSchema(BaseModel):
    """A single suggested resource for learning a missing skill."""

    title: str
    url: str


class MissingSkillSchema(BaseModel):
    """A taxonomy skill the candidate doesn't have yet, with a suggested learning resource."""

    skill: str
    resource: LearningResourceSchema | None = None


class MatchedSkillSchema(BaseModel):
    """A taxonomy skill the candidate already has, and where it was found."""

    skill: str
    sources: list[str] = Field(
        ..., description="Where this skill was found: 'resume', 'github', or both."
    )


class MissingSkillsBreakdown(BaseModel):
    """Missing skills, separated by priority — per the task's Must Have / Nice To Have requirement."""

    must_have: list[MissingSkillSchema] = Field(default_factory=list)
    nice_to_have: list[MissingSkillSchema] = Field(default_factory=list)


class SkillGapAnalysisResponse(BaseModel):
    """Response returned by POST /skills/gap."""

    target_role: str = Field(..., description="The canonical role name the request's target_role resolved to.")
    matched_skills: list[MatchedSkillSchema] = Field(default_factory=list)
    missing_skills: MissingSkillsBreakdown
    match_percentage: float = Field(
        ..., ge=0, le=100, description="Coverage of must-have skills for this role, 0-100."
    )
