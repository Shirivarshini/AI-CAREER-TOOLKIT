"""
Skill-Gap Engine — configuration models.

Why this file exists
---------------------
Same principle as `app.services.ats_scoring.config` /
`app.services.github_analysis.config`: tunable behavior lives here as a
named, typed, overridable field — never as a magic value inside the
matching/analysis logic.

This file specifically owns *skill-name normalization* (e.g. "js" and
"JavaScript" should be recognized as the same skill). This is
matching-algorithm configuration, distinct from the taxonomy data itself
(which roles require which skills) — that separation is deliberate: the
taxonomy is swappable storage (JSON today, PostgreSQL later, per the
task), while these aliases are part of the reusable matching engine and
apply uniformly regardless of where the taxonomy came from.

How it works
------------
`SkillGapConfig.skill_aliases` maps common variant spellings/abbreviations
to a single canonical form. `app/utils/skill_matching.py`'s
`normalize_skill()` lowercases, strips punctuation/whitespace, and then
applies this map — so both a resume's "JS" and a taxonomy's "JavaScript"
normalize to the same canonical string ("javascript") and are recognized
as a match.

Where future code should go
----------------------------
New synonym pairs (e.g. as new taxonomy roles/skills are added and gaps
in recognition are found) get added to `_DEFAULT_SKILL_ALIASES` — or
passed in via `SkillGapConfig(skill_aliases={...})` for a custom profile
(e.g. in tests).
"""

from pydantic import BaseModel, Field


class SkillGapConfig(BaseModel):
    """All tunable inputs to the Skill-Gap matching engine."""

    skill_aliases: dict[str, str] = Field(default_factory=lambda: dict(_DEFAULT_SKILL_ALIASES))
    must_have_weight_in_match_percentage: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description=(
            "How much must-have coverage alone determines match_percentage vs. "
            "blending in nice-to-have coverage. 1.0 = must-have coverage only "
            "(the PRD's priority framing: must-have skills are the readiness gate)."
        ),
    )


# Canonical form is the taxonomy's own spelling (see skill_taxonomy.json) so
# these aliases only need to normalize *toward* it, not both directions.
_DEFAULT_SKILL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node.js",
    "node": "node.js",
    "postgres": "postgresql",
    "psql": "postgresql",
    "py": "python",
    "golang": "go",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "dl": "deep learning",
    "aws cloud": "aws",
    "amazon web services": "aws",
    "gcp": "google cloud platform",
    "google cloud": "google cloud platform",
    "ci": "ci/cd",
    "cd": "ci/cd",
    "continuous integration": "ci/cd",
    "continuous deployment": "ci/cd",
    "html5": "html",
    "css3": "css",
    "restful api": "rest api design",
    "rest apis": "rest api design",
    "restful apis": "rest api design",
    "api design": "rest api design",
    "unit tests": "unit testing",
    "pytest": "unit testing",
    "sklearn": "scikit-learn",
    "tf": "tensorflow",
    "sql server": "sql",
    "mysql": "sql",
    "git/github": "git",
    "github": "git",
    "version control": "git",
    "docker containers": "docker",
    "containerization": "docker",
    "terraform iac": "terraform",
    "infrastructure as code": "terraform",
    "swiftui": "swift",
    "android studio": "kotlin",
    "power query": "excel",
    "microsoft excel": "excel",
    "data viz": "data visualization",
    "data analysis": "statistics",
}
