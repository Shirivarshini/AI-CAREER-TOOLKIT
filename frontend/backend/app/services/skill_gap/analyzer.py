"""
SkillGapAnalyzer — the Skill-Gap Engine's public entrypoint class.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.scorer.ATSScorer` and
`app.services.github_analysis.scorer.GitHubProfileScorer`: a single
reusable object that, given a `SkillGapContext` (what the candidate has)
and a `RoleTaxonomy` (what the role needs), returns matched skills,
missing must-have/nice-to-have skills (each with a learning resource),
and a match percentage. Per PRD 6.4: "diff logic between extracted and
required skills; static curated resource mapping" — that diff logic lives
entirely in this class, with no knowledge of HTTP, Pydantic, or how the
taxonomy was stored.

Usage
-----
    from app.services.skill_gap import SkillGapAnalyzer, SkillGapContext

    analyzer = SkillGapAnalyzer()  # or SkillGapAnalyzer(config=SkillGapConfig(...))
    result = analyzer.analyze(
        context=SkillGapContext(
            resume_skills=["Python", "SQL", "Docker"],
            github_skills=["Python", "JavaScript"],
            target_role="Backend Developer",
        ),
        taxonomy=taxonomy,  # a RoleTaxonomy, fetched via SkillTaxonomyRepository
    )
    print(result.match_percentage, result.missing_must_have)

This class has no FastAPI/Pydantic/storage dependency — it can be reused
from a script, a test, or a background job exactly as shown above; the
taxonomy is passed in already-fetched, so swapping the taxonomy's storage
backend (JSON today, PostgreSQL later) never requires touching this file.

Where future code should go
----------------------------
A new derived signal (e.g. per-skill weighting, or blending nice-to-have
into `match_percentage`) is a config-driven change inside `analyze()` —
see `SkillGapConfig.must_have_weight_in_match_percentage`.
"""

from app.services.skill_gap.config import SkillGapConfig
from app.services.skill_gap.types import (
    MatchedSkill,
    MissingSkill,
    RoleTaxonomy,
    SkillGapAnalysisResult,
    SkillGapContext,
    SkillRequirement,
)
from app.utils.skill_matching import build_normalized_skill_index, merge_skill_indexes, normalize_skill


class SkillGapAnalyzer:
    """
    Reusable skill-gap comparison engine.

    Compares a candidate's resume + GitHub skills against a role's
    must-have and nice-to-have skill taxonomy, and reports what's matched,
    what's missing (with a learning resource per missing skill), and an
    overall match percentage.
    """

    def __init__(self, config: SkillGapConfig | None = None) -> None:
        self._config = config or SkillGapConfig()

    def analyze(self, context: SkillGapContext, taxonomy: RoleTaxonomy) -> SkillGapAnalysisResult:
        """Run the resume/GitHub-vs-taxonomy diff and return the full result."""
        aliases = self._config.skill_aliases

        candidate_index = merge_skill_indexes(
            build_normalized_skill_index(context.resume_skills, source="resume", skill_aliases=aliases),
            build_normalized_skill_index(context.github_skills, source="github", skill_aliases=aliases),
        )

        matched_skills: list[MatchedSkill] = []
        missing_must_have: list[MissingSkill] = []
        missing_nice_to_have: list[MissingSkill] = []

        matched_must_have_count = 0
        for requirement in taxonomy.must_have:
            if self._is_matched(requirement, candidate_index, aliases, matched_skills):
                matched_must_have_count += 1
            else:
                missing_must_have.append(MissingSkill(skill=requirement.skill, resource=requirement.resource))

        matched_nice_to_have_count = 0
        for requirement in taxonomy.nice_to_have:
            if self._is_matched(requirement, candidate_index, aliases, matched_skills):
                matched_nice_to_have_count += 1
            else:
                missing_nice_to_have.append(
                    MissingSkill(skill=requirement.skill, resource=requirement.resource)
                )

        match_percentage = self._compute_match_percentage(
            matched_must_have_count,
            len(taxonomy.must_have),
            matched_nice_to_have_count,
            len(taxonomy.nice_to_have),
        )

        return SkillGapAnalysisResult(
            target_role=taxonomy.role,
            matched_skills=matched_skills,
            missing_must_have=missing_must_have,
            missing_nice_to_have=missing_nice_to_have,
            match_percentage=match_percentage,
        )

    def _is_matched(
        self,
        requirement: SkillRequirement,
        candidate_index: dict[str, set[str]],
        aliases: dict[str, str],
        matched_skills_out: list[MatchedSkill],
    ) -> bool:
        """Check one taxonomy requirement against the candidate's skill index; records a match if found."""
        normalized_requirement = normalize_skill(requirement.skill, aliases)
        sources = candidate_index.get(normalized_requirement)
        if not sources:
            return False
        matched_skills_out.append(MatchedSkill(skill=requirement.skill, sources=tuple(sorted(sources))))
        return True

    def _compute_match_percentage(
        self,
        matched_must_have: int,
        total_must_have: int,
        matched_nice_to_have: int,
        total_nice_to_have: int,
    ) -> float:
        """
        Weighted readiness percentage. By default (weight=1.0), this is
        purely must-have coverage — the PRD frames must-have skills as the
        readiness gate and nice-to-have as supplementary — but the weight
        is configurable (see `SkillGapConfig.must_have_weight_in_match_
        percentage`) for a blended score if that's ever wanted instead.
        """
        must_have_coverage = (matched_must_have / total_must_have * 100) if total_must_have else 100.0
        nice_to_have_coverage = (
            (matched_nice_to_have / total_nice_to_have * 100) if total_nice_to_have else 100.0
        )

        weight = self._config.must_have_weight_in_match_percentage
        blended = must_have_coverage * weight + nice_to_have_coverage * (1 - weight)
        return round(max(0.0, min(100.0, blended)), 2)
