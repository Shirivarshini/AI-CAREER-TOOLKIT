"""
GitHubProfileScorer — the GitHub Analysis Engine's public entrypoint class.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.scorer.ATSScorer`: a single reusable
object that, given a `GitHubProfileContext`, returns a 0–100 overall
score, a per-category breakdown, and deduplicated actionable
suggestions. Configurable end-to-end via `GitHubAnalysisConfig` —
nothing hardcoded inside this class.

Usage
-----
    from app.services.github_analysis import GitHubProfileScorer, GitHubProfileContext

    scorer = GitHubProfileScorer()  # or GitHubProfileScorer(config=GitHubAnalysisConfig(...))
    result = scorer.score(context)
    print(result.overall_score, result.suggestions)

This class has no FastAPI/Pydantic/HTTP dependency — `GitHubAnalysisService`
is responsible for fetching data via `GitHubClient` and building the
`GitHubProfileContext` this class consumes.

Where future code should go
----------------------------
A fifth scoring category means: write a new `SignalScorer` subclass, add
a matching weight field to `GitHubAnalysisWeights`, and register an
instance in `_default_scorers()` below.
"""

from app.config.settings import Settings
from app.services.github_analysis.activity_scorer import ActivityScorer
from app.services.github_analysis.base import SignalScorer
from app.services.github_analysis.config import GitHubAnalysisConfig, GitHubAnalysisWeights
from app.services.github_analysis.readme_quality_scorer import ReadmeQualityScorer
from app.services.github_analysis.repository_portfolio_scorer import RepositoryPortfolioScorer
from app.services.github_analysis.top_repos_scorer import TopRepositoriesScorer
from app.services.github_analysis.types import (
    CategoryScoreResult,
    GitHubCategory,
    GitHubProfileContext,
    GitHubScoringResult,
)


def build_github_config_from_settings(settings: Settings) -> GitHubAnalysisConfig:
    """
    Build a `GitHubAnalysisConfig` using category weights and API-call
    limits sourced from `Settings` (`.env` / `GITHUB_*`), while every other
    tunable keeps its default from `GitHubAnalysisConfig`.
    """
    weights = GitHubAnalysisWeights(
        repository_portfolio=settings.GITHUB_WEIGHT_REPOSITORY_PORTFOLIO,
        top_repositories=settings.GITHUB_WEIGHT_TOP_REPOSITORIES,
        readme_quality=settings.GITHUB_WEIGHT_README_QUALITY,
        activity=settings.GITHUB_WEIGHT_ACTIVITY,
    )
    return GitHubAnalysisConfig(
        weights=weights,
        top_repos_limit=settings.GITHUB_TOP_REPOS_LIMIT,
        readme_analysis_limit=settings.GITHUB_README_ANALYSIS_LIMIT,
    )


def _default_scorers(config: GitHubAnalysisConfig) -> dict[GitHubCategory, SignalScorer]:
    """Build the standard set of four category scorers from the given config."""
    return {
        GitHubCategory.REPOSITORY_PORTFOLIO: RepositoryPortfolioScorer(config),
        GitHubCategory.TOP_REPOSITORIES: TopRepositoriesScorer(config),
        GitHubCategory.README_QUALITY: ReadmeQualityScorer(config),
        GitHubCategory.ACTIVITY: ActivityScorer(config),
    }


class GitHubProfileScorer:
    """
    Reusable GitHub profile scoring engine.

    Computes a 0–100 overall profile score from four weighted categories
    (Repository Portfolio, Top Repositories, README Quality, Activity),
    each independently configurable via `GitHubAnalysisConfig`.
    """

    def __init__(
        self,
        config: GitHubAnalysisConfig | None = None,
        scorers: dict[GitHubCategory, SignalScorer] | None = None,
    ) -> None:
        self._config = config or GitHubAnalysisConfig()
        self._scorers = scorers or _default_scorers(self._config)

    def score(self, context: GitHubProfileContext) -> GitHubScoringResult:
        """Run all category scorers and aggregate into a final GitHubScoringResult."""
        weights = self._config.weights
        weight_map: dict[GitHubCategory, float] = {
            GitHubCategory.REPOSITORY_PORTFOLIO: weights.repository_portfolio,
            GitHubCategory.TOP_REPOSITORIES: weights.top_repositories,
            GitHubCategory.README_QUALITY: weights.readme_quality,
            GitHubCategory.ACTIVITY: weights.activity,
        }

        breakdown: dict[GitHubCategory, CategoryScoreResult] = {}
        for category, scorer in self._scorers.items():
            raw = scorer.score(context)
            breakdown[category] = CategoryScoreResult(
                category=category,
                score=round(raw.score, 2),
                weight=weight_map.get(category, 0.0),
                suggestions=raw.suggestions,
                details=raw.details,
            )

        overall_score = round(
            sum(result.score * result.weight for result in breakdown.values()), 2
        )
        # Clamp defensively — weights are normalized in config.py and each
        # category score is already clamped to [0, 100], but this guards
        # against floating-point drift ever producing e.g. 100.0001.
        overall_score = max(0.0, min(100.0, overall_score))

        return GitHubScoringResult(
            overall_score=overall_score,
            breakdown=breakdown,
            suggestions=self._aggregate_suggestions(breakdown),
        )

    @staticmethod
    def _aggregate_suggestions(breakdown: dict[GitHubCategory, CategoryScoreResult]) -> list[str]:
        """Flatten all categories' suggestions into one deduplicated, ordered list."""
        seen: set[str] = set()
        ordered: list[str] = []
        for result in breakdown.values():
            for suggestion in result.suggestions:
                if suggestion not in seen:
                    seen.add(suggestion)
                    ordered.append(suggestion)
        return ordered
