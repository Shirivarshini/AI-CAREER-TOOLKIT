"""
LinkedInProfileScorer — the LinkedIn Analysis Engine's public entrypoint class.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.scorer.ATSScorer` / `app.services.github_analysis.scorer.GitHubProfileScorer`:
a single reusable object that, given a `LinkedInProfileContext`, returns a
0–100 overall score, a per-category breakdown, and every other field the
task's required response shape needs (missing sections, per-section rewrite
suggestions, keyword suggestions, recruiter tips, a profile-strength label,
and prioritized next steps). Configurable end-to-end via
`LinkedInAnalysisConfig` — nothing hardcoded inside this class.

Usage
-----
    from app.services.linkedin_analysis import LinkedInProfileScorer, LinkedInProfileContext

    scorer = LinkedInProfileScorer()  # or LinkedInProfileScorer(config=LinkedInAnalysisConfig(...))
    result = scorer.score(context)
    print(result.overall_score, result.profile_strength, result.next_steps)

This class has no FastAPI/Pydantic/HTTP dependency — `LinkedInService` is
responsible for gathering section text (from pasted JSON or a parsed PDF
export) and building the `LinkedInProfileContext` this class consumes.

Where future code should go
----------------------------
A ninth scoring category means: write a new `CategoryScorer` subclass, add a
matching weight field to `LinkedInAnalysisWeights`, and register an instance
in `_default_scorers()` below.
"""

from app.config.settings import Settings
from app.services.linkedin_analysis.base import CategoryScorer
from app.services.linkedin_analysis.completeness_scorer import CompletenessScorer
from app.services.linkedin_analysis.config import LinkedInAnalysisConfig, LinkedInAnalysisWeights
from app.services.linkedin_analysis.insights import (
    build_keyword_suggestions,
    build_next_steps,
    build_recruiter_tips,
    classify_profile_strength,
)
from app.services.linkedin_analysis.section_scorer import SectionCategoryScorer
from app.services.linkedin_analysis.types import (
    CONTENT_CATEGORIES,
    CategoryScoreResult,
    LinkedInCategory,
    LinkedInProfileContext,
    LinkedInScoringResult,
)
from app.utils import linkedin_heuristics as heuristics


def build_linkedin_config_from_settings(settings: Settings) -> LinkedInAnalysisConfig:
    """
    Build a `LinkedInAnalysisConfig` using category weights sourced from the
    app's environment-configurable `Settings` (`.env` / `LINKEDIN_WEIGHT_*`),
    while every other tunable keeps its default from `LinkedInAnalysisConfig`.
    """
    weights = LinkedInAnalysisWeights(
        headline=settings.LINKEDIN_WEIGHT_HEADLINE,
        about=settings.LINKEDIN_WEIGHT_ABOUT,
        experience=settings.LINKEDIN_WEIGHT_EXPERIENCE,
        skills=settings.LINKEDIN_WEIGHT_SKILLS,
        education=settings.LINKEDIN_WEIGHT_EDUCATION,
        projects=settings.LINKEDIN_WEIGHT_PROJECTS,
        certifications=settings.LINKEDIN_WEIGHT_CERTIFICATIONS,
        completeness=settings.LINKEDIN_WEIGHT_COMPLETENESS,
    )
    return LinkedInAnalysisConfig(
        weights=weights,
        target_recommendation_count=settings.LINKEDIN_TARGET_RECOMMENDATION_COUNT,
    )


def _default_scorers(config: LinkedInAnalysisConfig) -> dict[LinkedInCategory, CategoryScorer]:
    """Build the standard set of eight category scorers from the given config."""
    return {
        LinkedInCategory.HEADLINE: SectionCategoryScorer(
            lambda ctx: ctx.headline, heuristics.score_headline, "headline"
        ),
        LinkedInCategory.ABOUT: SectionCategoryScorer(lambda ctx: ctx.about, heuristics.score_about, "about"),
        LinkedInCategory.EXPERIENCE: SectionCategoryScorer(
            lambda ctx: ctx.experience, heuristics.score_experience, "experience"
        ),
        LinkedInCategory.SKILLS: SectionCategoryScorer(lambda ctx: ctx.skills, heuristics.score_skills, "skills"),
        LinkedInCategory.EDUCATION: SectionCategoryScorer(
            lambda ctx: ctx.education, heuristics.score_education, "education"
        ),
        LinkedInCategory.PROJECTS: SectionCategoryScorer(
            lambda ctx: ctx.projects, heuristics.score_projects, "projects"
        ),
        LinkedInCategory.CERTIFICATIONS: SectionCategoryScorer(
            lambda ctx: ctx.certifications, heuristics.score_certifications, "certifications"
        ),
        LinkedInCategory.COMPLETENESS: CompletenessScorer(config),
    }


class LinkedInProfileScorer:
    """
    Reusable LinkedIn profile scoring engine.

    Computes a 0–100 overall profile score from eight weighted categories
    (Headline, About, Experience, Skills, Education, Projects,
    Certifications, Completeness), each independently configurable via
    `LinkedInAnalysisConfig`, plus keyword suggestions, recruiter tips, a
    profile-strength label, and prioritized next steps.
    """

    def __init__(
        self,
        config: LinkedInAnalysisConfig | None = None,
        scorers: dict[LinkedInCategory, CategoryScorer] | None = None,
    ) -> None:
        self._config = config or LinkedInAnalysisConfig()
        self._scorers = scorers or _default_scorers(self._config)

    def score(self, context: LinkedInProfileContext) -> LinkedInScoringResult:
        """Run all category scorers and aggregate into a final LinkedInScoringResult."""
        weights = self._config.weights
        weight_map: dict[LinkedInCategory, float] = {
            LinkedInCategory.HEADLINE: weights.headline,
            LinkedInCategory.ABOUT: weights.about,
            LinkedInCategory.EXPERIENCE: weights.experience,
            LinkedInCategory.SKILLS: weights.skills,
            LinkedInCategory.EDUCATION: weights.education,
            LinkedInCategory.PROJECTS: weights.projects,
            LinkedInCategory.CERTIFICATIONS: weights.certifications,
            LinkedInCategory.COMPLETENESS: weights.completeness,
        }

        breakdown: dict[LinkedInCategory, CategoryScoreResult] = {}
        for category, scorer in self._scorers.items():
            raw = scorer.score(context)
            breakdown[category] = CategoryScoreResult(
                category=category,
                score=round(raw.score, 2),
                weight=weight_map.get(category, 0.0),
                present=bool(raw.details.get("present", True)),
                suggestions=raw.suggestions,
                details=raw.details,
            )

        overall_score = round(sum(result.score * result.weight for result in breakdown.values()), 2)
        # Clamp defensively — weights are normalized in config.py and each
        # category score is already clamped to [0, 100], but this guards
        # against floating-point drift ever producing e.g. 100.0001.
        overall_score = max(0.0, min(100.0, overall_score))

        missing_sections = [category for category in CONTENT_CATEGORIES if not breakdown[category].present]
        rewrite_suggestions = {
            category: breakdown[category].suggestions for category in CONTENT_CATEGORIES
        }

        return LinkedInScoringResult(
            overall_score=overall_score,
            breakdown=breakdown,
            missing_sections=missing_sections,
            rewrite_suggestions=rewrite_suggestions,
            keyword_suggestions=build_keyword_suggestions(context, self._config),
            recruiter_tips=build_recruiter_tips(context, breakdown, self._config),
            profile_strength=classify_profile_strength(overall_score, self._config),
            next_steps=build_next_steps(breakdown, missing_sections, self._config),
        )
