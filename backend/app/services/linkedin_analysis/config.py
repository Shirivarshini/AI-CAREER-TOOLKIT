"""
LinkedIn Analysis Engine — configuration models.

Why this file exists
---------------------
Same principle as `app.services.ats_scoring.config` / `app.services.github_analysis.config`:
every tunable number used by the *engine-level* scoring/aggregation logic
(category weights, the Completeness category's targets, the score->label
mapping, the recruiter-keyword pool, how many next-steps to surface) lives
here as a named, typed, overridable field — never as a magic number inside a
scorer module.

This deliberately does NOT re-tune `app.utils.linkedin_heuristics`'s own
internal per-section thresholds (headline length cutoffs, cliché-phrase
lists, etc.) — those already exist as that module's own constants from the
prior part of this feature and are out of scope for this change; this file
only covers the new engine layer built on top of them (weights, the
Completeness signal, and the response-shaping logic in `insights.py`).

How it works
------------
- `LinkedInAnalysisWeights` holds the eight category weights, normalized to
  sum to 1.0 the same way `ATSScoringWeights`/`GitHubAnalysisWeights` do
  (auto-normalize + log a warning on a misconfigured `.env`, rather than
  silently producing a score outside 0–100).
- `LinkedInAnalysisConfig` bundles the weights with every other tunable:
  the Featured/Recommendations targets used by the Completeness category,
  the profile-strength score thresholds, the generic recruiter-keyword pool,
  and how many next-steps/keyword-suggestions to return. Sensible defaults
  make `LinkedInAnalysisConfig()` work out of the box.

Where future code should go
----------------------------
New tunable behavior (e.g. a per-role keyword pool, once `target_role` is
wired into keyword suggestions — see `insights.py`) should be added as a new
field here with a sensible default — never as a literal inside a scorer.
"""

import logging

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class LinkedInAnalysisWeights(BaseModel):
    """
    Relative importance of each scoring category. Must sum to 1.0 — if they
    don't, they are automatically normalized and a warning is logged.
    """

    headline: float = Field(default=0.10, ge=0)
    about: float = Field(default=0.15, ge=0)
    experience: float = Field(default=0.20, ge=0)
    skills: float = Field(default=0.15, ge=0)
    education: float = Field(default=0.10, ge=0)
    projects: float = Field(default=0.10, ge=0)
    certifications: float = Field(default=0.05, ge=0)
    completeness: float = Field(default=0.15, ge=0)

    @model_validator(mode="after")
    def _normalize(self) -> "LinkedInAnalysisWeights":
        total = (
            self.headline
            + self.about
            + self.experience
            + self.skills
            + self.education
            + self.projects
            + self.certifications
            + self.completeness
        )
        if total <= 0:
            raise ValueError("LinkedIn analysis weights must sum to a positive number.")
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "LinkedIn analysis weights sum to %.4f, not 1.0 — normalizing automatically.", total
            )
            self.headline /= total
            self.about /= total
            self.experience /= total
            self.skills /= total
            self.education /= total
            self.projects /= total
            self.certifications /= total
            self.completeness /= total
        return self


class LinkedInAnalysisConfig(BaseModel):
    """All tunable inputs to the LinkedIn Analysis Engine."""

    weights: LinkedInAnalysisWeights = Field(default_factory=LinkedInAnalysisWeights)

    # --- Completeness category (see completeness_scorer.py) ---
    target_recommendation_count: int = Field(
        default=2,
        gt=0,
        description="Number of LinkedIn recommendations that earns a full recommendations sub-score.",
    )

    # --- Profile strength label (see insights.py:classify_profile_strength) ---
    # Descending (score_threshold, label) pairs — the first threshold the
    # overall score meets or exceeds wins. Must be sorted descending by
    # threshold and end in a catch-all (threshold 0.0).
    profile_strength_thresholds: tuple[tuple[float, str], ...] = (
        (85.0, "Excellent"),
        (70.0, "Strong"),
        (50.0, "Needs Improvement"),
        (0.0, "Weak"),
    )

    # --- Keyword suggestions (see insights.py:build_keyword_suggestions) ---
    # A generic, role-agnostic pool of high-value recruiter-search /
    # ATS-friendly terms checked for absence across headline + about +
    # skills. Deliberately generic (no target-role input is consumed yet —
    # see LinkedInProfileContext.target_role's docstring); a per-role pool
    # sourced from the Skill-Gap module's taxonomy is a natural future
    # replacement for this default.
    recruiter_keyword_pool: tuple[str, ...] = (
        "leadership", "cross-functional", "stakeholder management", "data-driven",
        "agile", "scalable", "cloud", "automation", "mentorship", "collaboration",
        "problem-solving", "communication", "product strategy", "roadmap",
        "optimization", "analytics",
    )  # fmt: skip
    max_keyword_suggestions: int = Field(
        default=8, gt=0, description="Maximum number of missing-keyword suggestions to return."
    )

    # --- Prioritization (see insights.py:build_next_steps) ---
    next_steps_count: int = Field(
        default=5, gt=0, description="Maximum number of prioritized next-step suggestions to return."
    )
