"""
Response-shaping helpers: profile strength label, keyword suggestions,
recruiter tips, and prioritized next steps.

Why this file exists
---------------------
`LinkedInProfileScorer.score()` (in `scorer.py`) is responsible for
per-category scoring and weighted aggregation — the same responsibility
`ATSScorer`/`GitHubProfileScorer` have. This module holds the additional
response-shaping logic the task's required output adds on top of that
(`profile_strength`, `keyword_suggestions`, `recruiter_tips`, `next_steps`),
kept separate so `scorer.py` stays focused on scoring/weighting and these
pure functions stay independently testable.

Where future code should go
----------------------------
`build_keyword_suggestions` currently uses `config.recruiter_keyword_pool`
(a generic, role-agnostic list) because `LinkedInProfileContext.target_role`
isn't consumed by any scorer yet. Once a target role is supplied end-to-end
(mirroring the Skill-Gap Advisor's per-role taxonomy in
`app/services/skill_gap`), swap this function's keyword source for that
role's taxonomy — the function's signature and return shape don't need to
change.
"""

from app.services.linkedin_analysis.config import LinkedInAnalysisConfig
from app.services.linkedin_analysis.types import (
    CONTENT_CATEGORIES,
    CategoryScoreResult,
    LinkedInCategory,
    LinkedInProfileContext,
)


def classify_profile_strength(overall_score: float, config: LinkedInAnalysisConfig) -> str:
    """Map the overall 0-100 score onto a human-readable label via `config.profile_strength_thresholds`."""
    for threshold, label in config.profile_strength_thresholds:
        if overall_score >= threshold:
            return label
    # Unreachable if the config's thresholds end in a 0.0 catch-all (the
    # default does), but guards against a misconfigured override.
    return "Weak"


def build_keyword_suggestions(context: LinkedInProfileContext, config: LinkedInAnalysisConfig) -> list[str]:
    """
    Surface high-value recruiter-search keywords absent from the headline,
    about, and skills sections combined — a lightweight, role-agnostic proxy
    for the PRD's "recruiter visibility" / "ATS friendliness" signals.
    """
    combined_text = " ".join(
        filter(None, [context.headline, context.about, context.skills])
    ).lower()
    if not combined_text.strip():
        return []

    missing = [keyword for keyword in config.recruiter_keyword_pool if keyword not in combined_text]
    return missing[: config.max_keyword_suggestions]


def build_recruiter_tips(
    context: LinkedInProfileContext,
    breakdown: dict[LinkedInCategory, CategoryScoreResult],
    config: LinkedInAnalysisConfig,
) -> list[str]:
    """
    General, profile-wide recruiter-visibility tips — distinct from
    `rewrite_suggestions`, which are specific to one section's content.
    """
    completeness = breakdown.get(LinkedInCategory.COMPLETENESS)
    details = completeness.details if completeness else {}

    tips: list[str] = []

    if not details.get("featured_present", False):
        tips.append(
            "Turn on 'Open to Work' (visible to recruiters only, if preferred) to appear in "
            "more recruiter searches."
        )

    if details.get("recommendations_count", 0) < config.target_recommendation_count:
        tips.append(
            "Request recommendations from former managers or collaborators — profiles with "
            "recommendations are viewed as more credible by recruiters."
        )

    skills_result = breakdown.get(LinkedInCategory.SKILLS)
    if skills_result and skills_result.present and skills_result.score < 70:
        tips.append(
            "Add more specific, searchable skills — LinkedIn's recruiter search matches "
            "heavily on the Skills section."
        )

    headline_result = breakdown.get(LinkedInCategory.HEADLINE)
    if headline_result and headline_result.present and headline_result.score < 70:
        tips.append(
            "A stronger headline (role + key skills, not just a job title) improves how often "
            "you appear in recruiter search results."
        )

    tips.append("Keep your profile's visibility set to public so it's indexed by search engines and recruiters.")

    return tips


def build_next_steps(
    breakdown: dict[LinkedInCategory, CategoryScoreResult],
    missing_sections: list[LinkedInCategory],
    config: LinkedInAnalysisConfig,
) -> list[str]:
    """
    A single prioritized action list: missing sections first (the highest-
    leverage, easiest fix), then the lowest-scoring present categories'
    top suggestion, deduplicated and capped at `config.next_steps_count`.
    """
    steps: list[str] = []
    seen: set[str] = set()

    def _add(suggestion: str) -> None:
        if suggestion not in seen:
            seen.add(suggestion)
            steps.append(suggestion)

    # 1. Missing core sections first — always the highest-leverage fix.
    for category in CONTENT_CATEGORIES:
        if category in missing_sections and breakdown[category].suggestions:
            _add(breakdown[category].suggestions[0])
        if len(steps) >= config.next_steps_count:
            return steps

    # 2. Then present-but-weak categories, worst-scoring first.
    present_categories = sorted(
        (result for result in breakdown.values() if result.present),
        key=lambda result: result.score,
    )
    for result in present_categories:
        if result.suggestions:
            _add(result.suggestions[0])
        if len(steps) >= config.next_steps_count:
            break

    return steps[: config.next_steps_count]
