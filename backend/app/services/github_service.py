"""
GitHub Profile Analysis — service layer (fetch -> normalize -> score -> cache).

Why this file exists
---------------------
The service layer coordinates `GitHubClient` (raw GitHub REST API access),
the framework-agnostic `GitHubProfileScorer` engine, and `CacheBackend` —
without any of those concerns' implementation details leaking into the
API router. The router stays a thin HTTP adapter; this is where the
"recipe" for handling a GitHub analysis request lives, matching the
pattern established by `ResumeService`.

How it works
------------
`GitHubAnalysisService.analyze_profile()`:
  1. Checks the cache (keyed by normalized username) — a hit short-
     circuits everything else, per the task's caching requirement and to
     conserve GitHub's rate limit.
  2. Fetches the user profile (raises `GitHubUserNotFoundError` on a
     missing account — PRD 5.2).
  3. Concurrently fetches the user's repositories and recent public
     events (`asyncio.gather`), then concurrently fetches READMEs for the
     top-ranked repositories.
  4. Normalizes everything into a `GitHubProfileContext`.
  5. Runs `GitHubProfileScorer.score()` (CPU-bound but cheap — no
     `asyncio.to_thread` needed, unlike the ATS engine's regex-heavy text
     scoring over full resumes).
  6. Maps the result onto `GitHubAnalysisResponse`, caches it, and
     returns it.

An empty-but-valid profile (0 public repos) is not an error — it flows
through scoring normally and surfaces as a low score with suggestions,
per PRD 5.2's "clear message rather than a generic error" (an error here
would be misleading: the *username* is valid, the *profile* is just thin).
A single failed README fetch (e.g. a transient GitHub error on one repo)
is logged and treated as "no README" rather than failing the whole
analysis — one repo's hiccup shouldn't block the rest of the report.

Where future code should go
----------------------------
When `GitHubAnalysis` persistence is added (PRD's data model, section 11),
inject a repository (bound to `Depends(get_db)`) here alongside the
client/cache, and save the result after scoring — the fetch/normalize/
score flow itself should not need to change.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.github_client import GitHubClient
from app.config.settings import Settings, get_settings
from app.core.cache import CacheBackend, get_cache_backend
from app.core.database import get_db
from app.core.exceptions import AppException
from app.repositories.report_repository import GitHubReportRepository
from app.schemas.github import (
    GitHubAnalysisResponse,
    GitHubProfileScoreResult,
    GitHubProfileStatistics,
    GitHubScoreBreakdown,
    GitHubScoreCategoryResult,
    LanguageDistributionEntry,
    RepositoryHighlight,
)
from app.services.github_analysis import (
    GitHubAnalysisConfig,
    GitHubProfileContext,
    GitHubProfileScorer,
    RepoSummary,
    build_github_config_from_settings,
)
from app.services.github_analysis.types import GitHubCategory, GitHubScoringResult

logger = logging.getLogger(__name__)


def _parse_github_datetime(value: str | None) -> datetime | None:
    """Parse GitHub's ISO-8601 'Z'-suffixed timestamps into aware datetimes."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_repo_summary(raw: dict) -> RepoSummary:
    return RepoSummary(
        name=raw.get("name", "unknown"),
        description=raw.get("description"),
        stars=raw.get("stargazers_count", 0) or 0,
        forks=raw.get("forks_count", 0) or 0,
        language=raw.get("language"),
        is_fork=bool(raw.get("fork", False)),
        pushed_at=_parse_github_datetime(raw.get("pushed_at")),
        html_url=raw.get("html_url", ""),
    )


class GitHubAnalysisService:
    """Orchestrates GitHub profile fetching, caching, and scoring."""

    def __init__(
        self,
        client: GitHubClient,
        cache: CacheBackend,
        settings: Settings,
        scorer: GitHubProfileScorer,
        config: GitHubAnalysisConfig,
        report_repository: GitHubReportRepository,
    ) -> None:
        self._client = client
        self._cache = cache
        self._settings = settings
        self._scorer = scorer
        self._config = config
        self._report_repository = report_repository

    async def analyze_profile(self, username: str, user_id: uuid.UUID | None = None) -> GitHubAnalysisResponse:
        """
        Fetch, score, and return a GitHub profile analysis, using a cached
        result when available.

        Raises (via the shared AppException hierarchy, handled globally):
          - GitHubUserNotFoundError — no such GitHub account
          - RateLimitExceededError — GitHub API rate limit hit
          - ExternalServiceError — GitHub API unreachable / unexpected error
        """
        cache_key = self._cache_key(username)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.info("GitHub analysis cache hit for '%s'", username)
            await self._save_report(username, cached, user_id)
            return cached

        user = await self._client.get_user(username)

        repos_raw, events_raw = await asyncio.gather(
            self._client.list_repos(username),
            self._client.list_public_events(username),
        )
        repos = [_to_repo_summary(r) for r in repos_raw]

        top_repos = self._select_top_repos(repos)
        readme_targets = top_repos[: self._config.readme_analysis_limit]
        readme_analyzed_repos = await self._attach_readmes(username, readme_targets)

        context = GitHubProfileContext(
            username=user.get("login", username),
            public_repos_count=user.get("public_repos", len(repos)),
            followers=user.get("followers", 0),
            account_created_at=_parse_github_datetime(user.get("created_at")),
            repos=repos,
            top_repos=top_repos,
            readme_analyzed_repos=readme_analyzed_repos,
            recent_active_dates=self._extract_active_dates(events_raw),
            activity_lookback_days=self._config.activity_lookback_days,
        )

        scoring_result = self._scorer.score(context)
        logger.info("GitHub profile score for '%s': %.2f/100", username, scoring_result.overall_score)

        response = self._build_response(user, context, scoring_result)
        await self._set_cached(cache_key, response)
        await self._save_report(username, response, user_id)
        return response

    async def _save_report(
        self, username: str, response: GitHubAnalysisResponse, user_id: uuid.UUID | None
    ) -> None:
        """
        Persist a report row for a successful analysis (cached or freshly
        scored). Never lets a storage failure surface as a failed request —
        logged and swallowed instead.
        """
        try:
            await self._report_repository.create(
                user_id=user_id,
                username=response.username,
                input_data={"username": username},
                score=response.profile_score.overall_score,
                breakdown_json=response.model_dump(mode="json"),
            )
        except Exception:
            logger.exception("Failed to save GitHub analysis report for '%s'", username)

    # --- Data shaping -----------------------------------------------------

    def _select_top_repos(self, repos: list[RepoSummary]) -> list[RepoSummary]:
        """
        Rank the user's own (non-fork) repos by engagement (stars, then
        forks, then recency) and take the configured top slice — the
        pinned-repo proxy documented in `top_repos_scorer.py`.
        """
        own_repos = [r for r in repos if not r.is_fork]
        ranked = sorted(
            own_repos,
            key=lambda r: (r.stars, r.forks, r.pushed_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        return ranked[: self._config.top_repos_limit]

    async def _attach_readmes(self, username: str, repos: list[RepoSummary]) -> list[RepoSummary]:
        """Fetch READMEs for the given repos concurrently; a single failure degrades to 'no README'."""

        async def _fetch(repo: RepoSummary) -> RepoSummary:
            try:
                readme_text = await self._client.get_readme_text(username, repo.name)
            except AppException as exc:
                logger.warning("README fetch failed for %s/%s: %s", username, repo.name, exc.message)
                readme_text = None
            return RepoSummary(
                name=repo.name,
                description=repo.description,
                stars=repo.stars,
                forks=repo.forks,
                language=repo.language,
                is_fork=repo.is_fork,
                pushed_at=repo.pushed_at,
                html_url=repo.html_url,
                readme_text=readme_text,
            )

        if not repos:
            return []
        return list(await asyncio.gather(*(_fetch(r) for r in repos)))

    def _extract_active_dates(self, events: list[dict]) -> list:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._config.activity_lookback_days)

        dates: set = set()
        for event in events:
            created_at = _parse_github_datetime(event.get("created_at"))
            if created_at and created_at >= cutoff:
                dates.add(created_at.date())
        return sorted(dates, reverse=True)

    # --- Response mapping ---------------------------------------------------

    def _build_response(
        self, user: dict, context: GitHubProfileContext, result: GitHubScoringResult
    ) -> GitHubAnalysisResponse:
        portfolio_details = result.breakdown[GitHubCategory.REPOSITORY_PORTFOLIO].details
        readme_details = result.breakdown[GitHubCategory.README_QUALITY].details

        readme_by_name = {r.name: r for r in context.readme_analyzed_repos}
        top_repositories = [
            RepositoryHighlight(
                name=repo.name,
                url=repo.html_url,
                description=repo.description,
                stars=repo.stars,
                forks=repo.forks,
                language=repo.language,
                has_readme=bool(readme_by_name.get(repo.name) and readme_by_name[repo.name].readme_text),
                last_pushed_at=repo.pushed_at,
            )
            for repo in context.top_repos
        ]

        statistics = GitHubProfileStatistics(
            public_repos=context.public_repos_count,
            non_fork_repos=portfolio_details.get("non_fork_repo_count", 0),
            total_stars=portfolio_details.get("total_stars", 0),
            total_forks=portfolio_details.get("total_forks", 0),
            followers=context.followers,
            account_created_at=context.account_created_at,
            language_distribution=[
                LanguageDistributionEntry(**entry)
                for entry in portfolio_details.get("language_distribution", [])
            ],
            active_days_recent_window=len(context.recent_active_dates),
            recent_activity_window_days=context.activity_lookback_days,
        )

        def _category(name: GitHubCategory) -> GitHubScoreCategoryResult:
            cat = result.breakdown[name]
            return GitHubScoreCategoryResult(score=cat.score, weight=cat.weight, suggestions=cat.suggestions)

        profile_score = GitHubProfileScoreResult(
            overall_score=result.overall_score,
            breakdown=GitHubScoreBreakdown(
                repository_portfolio=_category(GitHubCategory.REPOSITORY_PORTFOLIO),
                top_repositories=_category(GitHubCategory.TOP_REPOSITORIES),
                readme_quality=_category(GitHubCategory.README_QUALITY),
                activity=_category(GitHubCategory.ACTIVITY),
            ),
            suggestions=result.suggestions,
        )

        _ = readme_details  # currently only repos_missing_readmes, already reflected in suggestions

        return GitHubAnalysisResponse(
            username=user.get("login", context.username),
            profile_url=user.get("html_url", f"https://github.com/{context.username}"),
            avatar_url=user.get("avatar_url"),
            statistics=statistics,
            top_repositories=top_repositories,
            profile_score=profile_score,
        )

    # --- Caching --------------------------------------------------------------

    @staticmethod
    def _cache_key(username: str) -> str:
        return f"github_analysis:{username.strip().lower()}"

    async def _get_cached(self, cache_key: str) -> GitHubAnalysisResponse | None:
        raw = await self._cache.get(cache_key)
        if raw is None:
            return None
        try:
            return GitHubAnalysisResponse.model_validate_json(raw)
        except ValueError:
            logger.warning("Discarding malformed cached GitHub analysis for key '%s'", cache_key)
            return None

    async def _set_cached(self, cache_key: str, response: GitHubAnalysisResponse) -> None:
        await self._cache.set(
            cache_key, response.model_dump_json(), self._settings.GITHUB_ANALYSIS_CACHE_TTL_SECONDS
        )


def get_github_analysis_service(db: AsyncSession = Depends(get_db)) -> GitHubAnalysisService:
    """
    FastAPI dependency factory for GitHubAnalysisService.

    The GitHub client and cache backend are both process-wide singletons
    reused across requests. `db` is only used to build the
    `GitHubReportRepository` that persists each successful analysis.
    """
    settings = get_settings()
    config = build_github_config_from_settings(settings)
    return GitHubAnalysisService(
        client=GitHubClient(settings),
        cache=get_cache_backend(),
        settings=settings,
        scorer=GitHubProfileScorer(config=config),
        config=config,
        report_repository=GitHubReportRepository(db),
    )
