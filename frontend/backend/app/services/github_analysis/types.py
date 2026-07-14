"""
GitHub Analysis Engine — internal domain types.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.types`: the scoring engine is reusable
outside of FastAPI, so its inputs/outputs are plain `dataclasses`, not
Pydantic API schemas. `GitHubAnalysisService` maps `GitHubScoringResult`
(defined here) onto `app.schemas.github`'s Pydantic response — the engine
itself never imports Pydantic or FastAPI.

How it works
------------
- `RepoSummary` is one repository's normalized, already-fetched data
  (GitHub's raw JSON shape flattened to just what scorers need).
- `GitHubProfileContext` is the single input to the engine: everything a
  category scorer might need, already fetched and normalized by
  `GitHubAnalysisService` — scorers never make HTTP calls themselves.
- `RawSignalScore` / `CategoryScoreResult` / `GitHubScoringResult` follow
  the exact same weighting pattern as the ATS engine's `RawCategoryScore`
  / `CategoryScoreResult` / `ATSScoringResult`.

Where future code should go
----------------------------
A new scoring category needs a new `SignalScorer` subclass producing a
`RawSignalScore` — this file only changes if a category needs a genuinely
new output shape beyond score/suggestions/details.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class GitHubCategory(str, Enum):
    """The four GitHub profile scoring categories."""

    REPOSITORY_PORTFOLIO = "repository_portfolio"
    TOP_REPOSITORIES = "top_repositories"
    README_QUALITY = "readme_quality"
    ACTIVITY = "activity"


@dataclass(frozen=True)
class RepoSummary:
    """One repository's normalized data, as needed by scorers."""

    name: str
    description: str | None
    stars: int
    forks: int
    language: str | None
    is_fork: bool
    pushed_at: datetime | None
    html_url: str
    readme_text: str | None = None  # populated only for the README-analysis slice


@dataclass(frozen=True)
class GitHubProfileContext:
    """Everything a category scorer might need to compute its score."""

    username: str
    public_repos_count: int
    followers: int
    account_created_at: datetime | None
    repos: list[RepoSummary]
    top_repos: list[RepoSummary]  # engagement-ranked slice; proxy for "pinned" (see top_repos_scorer.py)
    readme_analyzed_repos: list[RepoSummary]  # subset of top_repos with readme_text populated
    recent_active_dates: list[date]  # distinct dates with public activity, within the lookback window
    activity_lookback_days: int


@dataclass(frozen=True)
class RawSignalScore:
    """
    A single category scorer's output, before the engine applies weighting.

    `score` must be in the 0–100 range. `details` is a free-form bag for
    category-specific structured data the engine surfaces at the top
    level (e.g. `language_distribution`, `repos_missing_readmes`).
    """

    score: float
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CategoryScoreResult:
    """A `RawSignalScore` combined with the weight the engine applied to it."""

    category: GitHubCategory
    score: float
    weight: float
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GitHubScoringResult:
    """The GitHub Analysis Engine's final output for a single profile."""

    overall_score: float
    breakdown: dict[GitHubCategory, CategoryScoreResult]
    suggestions: list[str]
