"""
GitHub Analysis Engine package.

Framework-agnostic, mirroring `app.services.ats_scoring`: no dependency
on FastAPI, Pydantic request/response models, HTTP, or the database. It
takes an already-fetched `GitHubProfileContext` + config in, and returns
plain dataclasses out — reusable outside the API (script, CLI, background
job), not just from `GitHubAnalysisService`.

Modules:
    config.py                       - GitHubAnalysisWeights / GitHubAnalysisConfig (all tunables)
    types.py                        - RawSignalScore / CategoryScoreResult / GitHubProfileContext / GitHubScoringResult
    base.py                         - SignalScorer abstract base class
    repository_portfolio_scorer.py  - Repositories / Stars / Forks / Languages
    top_repos_scorer.py             - Top ("pinned"-proxy) repositories
    readme_quality_scorer.py        - README content quality
    activity_scorer.py              - Recent contribution activity
    scorer.py                       - GitHubProfileScorer, the public entrypoint class
"""

from app.services.github_analysis.config import GitHubAnalysisConfig, GitHubAnalysisWeights
from app.services.github_analysis.scorer import GitHubProfileScorer, build_github_config_from_settings
from app.services.github_analysis.types import (
    GitHubCategory,
    GitHubProfileContext,
    GitHubScoringResult,
    RepoSummary,
)

__all__ = [
    "GitHubProfileScorer",
    "GitHubAnalysisConfig",
    "GitHubAnalysisWeights",
    "GitHubCategory",
    "GitHubProfileContext",
    "GitHubScoringResult",
    "RepoSummary",
    "build_github_config_from_settings",
]
