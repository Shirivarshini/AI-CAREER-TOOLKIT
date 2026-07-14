"""
GitHub Analysis Engine — configuration models.

Why this file exists
---------------------
Same principle as `app.services.ats_scoring.config`: every tunable number
used by the scoring logic (category weights, target counts, thresholds)
lives here as a named, typed, overridable field — never as a magic number
inside a scorer module.

How it works
------------
- `GitHubAnalysisWeights` holds the four category weights, normalized to
  sum to 1.0 the same way `ATSScoringWeights` does (auto-normalize + log
  a warning on a misconfigured `.env`, rather than silently producing a
  score outside 0–100).
- `GitHubAnalysisConfig` bundles the weights with every other tunable:
  target repo/star/language counts, README-quality thresholds, activity
  lookback window, etc. Sensible defaults make `GitHubAnalysisConfig()`
  work out of the box.

Where future code should go
----------------------------
New tunable behavior (e.g. a per-role "expected languages" list, once the
Skill-Gap module exists) should be added as a new field here with a
sensible default — never as a literal inside a scorer.
"""

import logging

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class GitHubAnalysisWeights(BaseModel):
    """
    Relative importance of each scoring category. Must sum to 1.0 — if they
    don't, they are automatically normalized and a warning is logged.
    """

    repository_portfolio: float = Field(default=0.25, ge=0)
    top_repositories: float = Field(default=0.20, ge=0)
    readme_quality: float = Field(default=0.30, ge=0)
    activity: float = Field(default=0.25, ge=0)

    @model_validator(mode="after")
    def _normalize(self) -> "GitHubAnalysisWeights":
        total = self.repository_portfolio + self.top_repositories + self.readme_quality + self.activity
        if total <= 0:
            raise ValueError("GitHub analysis weights must sum to a positive number.")
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "GitHub analysis weights sum to %.4f, not 1.0 — normalizing automatically.", total
            )
            self.repository_portfolio /= total
            self.top_repositories /= total
            self.readme_quality /= total
            self.activity /= total
        return self


class GitHubAnalysisConfig(BaseModel):
    """All tunable inputs to the GitHub Analysis Engine."""

    weights: GitHubAnalysisWeights = Field(default_factory=GitHubAnalysisWeights)

    # --- Repository Portfolio ---
    target_repo_count: int = Field(
        default=8, gt=0, description="Non-fork repo count that earns a full repo-count sub-score."
    )
    target_star_count: int = Field(
        default=20, gt=0, description="Total stars across repos that earns a full stars sub-score."
    )
    target_language_count: int = Field(
        default=3, gt=0, description="Distinct primary languages that earns a full diversity sub-score."
    )

    # --- Top Repositories (pinned-repo proxy — see top_repos_scorer.py) ---
    top_repos_limit: int = Field(default=6, gt=0)
    min_description_length: int = Field(
        default=20, gt=0, description="Below this, a repo description is treated as effectively missing."
    )

    # --- README Quality ---
    readme_analysis_limit: int = Field(default=5, gt=0)
    min_readme_word_count: int = Field(default=50, gt=0)
    good_readme_word_count: int = Field(
        default=150, gt=0, description="Word count that alone earns a strong length sub-score."
    )
    readme_signal_sections: tuple[str, ...] = (
        "install", "usage", "getting started", "example", "how to", "setup", "demo",
    )

    # --- Activity ---
    activity_lookback_days: int = Field(
        default=90,
        gt=0,
        description="GitHub's public events API only returns recent activity (~90 days); "
        "see github_client.py's module docstring for why this can't be a full history.",
    )
    target_active_days: int = Field(
        default=10, gt=0, description="Distinct active days within the lookback window for a full score."
    )
