"""
Completeness category scorer.

Why this file exists
---------------------
Per the task's "Analyze" list: Profile Completeness, Featured Section, and
Recommendations Section. None of these are single pasted/parsed sections
scored on their own content the way Headline or About are — they're
cross-cutting signals about the profile as a whole, so they get their own
`CategoryScorer` rather than being force-fit into `SectionCategoryScorer`.

How it works
------------
Three independent 0–100 sub-signals, averaged with equal weight:
  1. **Section presence** — the fraction of the seven core content sections
     (Headline, About, Experience, Skills, Education, Projects,
     Certifications) that have any content at all. This is the direct
     "Profile Completeness" signal from the task's Analyze list.
  2. **Featured section** — a flat 100/0 on whether `context.featured` has
     content, per the task's "Featured Section" signal.
  3. **Recommendations** — how many recommendations were provided
     (`context.recommendations`, split the same way `linkedin_heuristics`
     splits comma/pipe/line-separated lists) against
     `config.target_recommendation_count`, capped at 100%, per the task's
     "Recommendations Section" signal.

Where future code should go
----------------------------
If LinkedIn's "All-Star" completeness meter's exact rules are ever needed
(it also weighs profile photo, industry, location, and connection count —
none of which this module collects), add each as its own sub-signal here
rather than overloading one of the three above.
"""

import re

from app.services.linkedin_analysis.base import CategoryScorer
from app.services.linkedin_analysis.config import LinkedInAnalysisConfig
from app.services.linkedin_analysis.types import CONTENT_CATEGORIES, LinkedInProfileContext, RawSignalScore

_SECTION_TEXT_GETTERS = {
    "headline": lambda ctx: ctx.headline,
    "about": lambda ctx: ctx.about,
    "experience": lambda ctx: ctx.experience,
    "skills": lambda ctx: ctx.skills,
    "education": lambda ctx: ctx.education,
    "projects": lambda ctx: ctx.projects,
    "certifications": lambda ctx: ctx.certifications,
}

_ITEM_SPLIT_PATTERN = re.compile(r"[•\u2022]")
_ITEM_DELIMITER_PATTERN = re.compile(r"[,\n;|]")


def _count_items(text: str) -> int:
    """Same list-splitting convention as `app.utils.linkedin_heuristics._split_items`."""
    normalized = _ITEM_SPLIT_PATTERN.sub("\n", text)
    parts = _ITEM_DELIMITER_PATTERN.split(normalized)
    return len([item.strip() for item in parts if item.strip()])


class CompletenessScorer(CategoryScorer):
    """Scores overall profile completeness: core-section presence, Featured, and Recommendations."""

    def __init__(self, config: LinkedInAnalysisConfig) -> None:
        self._config = config

    def score(self, context: LinkedInProfileContext) -> RawSignalScore:
        present_sections = [
            name for name, getter in _SECTION_TEXT_GETTERS.items() if getter(context) and getter(context).strip()
        ]
        missing_sections = [name for name in _SECTION_TEXT_GETTERS if name not in present_sections]
        presence_score = (len(present_sections) / len(_SECTION_TEXT_GETTERS)) * 100

        featured_present = bool(context.featured and context.featured.strip())
        featured_score = 100.0 if featured_present else 0.0

        recommendation_count = _count_items(context.recommendations) if context.recommendations else 0
        recommendations_score = min(recommendation_count / self._config.target_recommendation_count, 1.0) * 100

        score = round((presence_score + featured_score + recommendations_score) / 3, 2)

        suggestions: list[str] = []
        if missing_sections:
            preview = ", ".join(missing_sections)
            suggestions.append(
                f"Your profile is missing: {preview}. A complete profile ranks higher in "
                "recruiter and LinkedIn search results."
            )
        if not featured_present:
            suggestions.append(
                "Add a Featured section highlighting your best work (a project, article, or "
                "post) — it's one of the first things visitors see below your About section."
            )
        if recommendation_count < self._config.target_recommendation_count:
            suggestions.append(
                f"You have {recommendation_count} recommendation(s); aim for at least "
                f"{self._config.target_recommendation_count} from managers, peers, or clients "
                "to build third-party credibility."
            )

        return RawSignalScore(
            score=score,
            suggestions=suggestions,
            details={
                "present": True,  # Completeness is a meta-category, never itself "missing"
                "missing_sections": missing_sections,
                "featured_present": featured_present,
                "recommendations_count": recommendation_count,
            },
        )
