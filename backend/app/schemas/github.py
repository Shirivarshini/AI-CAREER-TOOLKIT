"""
GitHub Analysis — Pydantic schemas.

Why this file exists
---------------------
Request/response contracts for the GitHub Profile Analysis feature,
separate from the generic `app/schemas/common.py`, following the same
pattern as `app/schemas/resume.py`.

Where future code should go
----------------------------
Future GitHub endpoints from the PRD's API spec get their own schemas
here, reusing `GitHubScoreCategoryResult` / `RepositoryHighlight` where
their shape overlaps.
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# GitHub usernames: alphanumeric or single hyphens, no leading/trailing/consecutive
# hyphens, max 39 characters — GitHub's own account-name rules.
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")


class GitHubAnalyzeRequest(BaseModel):
    """Request body for POST /github/analyze."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=39,
        description="A GitHub username (not a full profile URL).",
        examples=["octocat"],
    )

    @field_validator("username")
    @classmethod
    def _validate_username_format(cls, value: str) -> str:
        stripped = value.strip()
        if not _USERNAME_PATTERN.match(stripped):
            raise ValueError(
                "Invalid GitHub username format. Usernames may only contain alphanumeric "
                "characters and single hyphens, and cannot start or end with a hyphen."
            )
        return stripped


class LanguageDistributionEntry(BaseModel):
    """One language's share of the user's repositories, by primary language."""

    language: str
    repo_count: int = Field(..., ge=0)
    percentage: float = Field(..., ge=0, le=100)


class RepositoryHighlight(BaseModel):
    """A single repository surfaced in the response's top-repositories list."""

    name: str
    url: str
    description: str | None = None
    stars: int = Field(..., ge=0)
    forks: int = Field(..., ge=0)
    language: str | None = None
    has_readme: bool
    last_pushed_at: datetime | None = None


class GitHubProfileStatistics(BaseModel):
    """Raw statistics pulled from the GitHub REST API, per the task's 'Statistics' requirement."""

    public_repos: int = Field(..., ge=0, description="Total public repositories, as reported by GitHub.")
    non_fork_repos: int = Field(..., ge=0, description="Repositories owned and not forked from elsewhere.")
    total_stars: int = Field(..., ge=0)
    total_forks: int = Field(..., ge=0)
    followers: int = Field(..., ge=0)
    account_created_at: datetime | None = None
    language_distribution: list[LanguageDistributionEntry] = Field(default_factory=list)
    active_days_recent_window: int = Field(
        ..., ge=0, description="Distinct days with public activity within the recent-activity window."
    )
    recent_activity_window_days: int = Field(
        ..., gt=0, description="Size (in days) of the recent-activity window used above."
    )


class GitHubScoreCategoryResult(BaseModel):
    """A single GitHub scoring category's result (e.g. README Quality, Activity)."""

    score: float = Field(..., ge=0, le=100, description="Category score, 0-100.")
    weight: float = Field(..., ge=0, le=1, description="This category's weight in the overall score.")
    suggestions: list[str] = Field(default_factory=list, description="Actionable fixes for this category.")


class GitHubScoreBreakdown(BaseModel):
    """Per-category breakdown of the overall profile score."""

    repository_portfolio: GitHubScoreCategoryResult
    top_repositories: GitHubScoreCategoryResult = Field(
        ..., description="Proxy for 'Pinned Repositories' — see README in the GitHub analysis package."
    )
    readme_quality: GitHubScoreCategoryResult
    activity: GitHubScoreCategoryResult


class GitHubProfileScoreResult(BaseModel):
    """The full profile-strength scoring result, per the task's 'Profile Score' requirement."""

    overall_score: float = Field(..., ge=0, le=100, description="Weighted overall profile score, 0-100.")
    breakdown: GitHubScoreBreakdown
    suggestions: list[str] = Field(
        ..., description="All actionable fixes across categories, deduplicated, per the task's 'Suggestions' requirement."
    )


class GitHubAnalysisResponse(BaseModel):
    """Response returned by POST /github/analyze."""

    username: str
    profile_url: str
    avatar_url: str | None = None
    statistics: GitHubProfileStatistics
    top_repositories: list[RepositoryHighlight] = Field(
        default_factory=list,
        description="Engagement-ranked 'best work' repositories — see top_repositories score category.",
    )
    profile_score: GitHubProfileScoreResult
