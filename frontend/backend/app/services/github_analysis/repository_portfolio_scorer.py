"""
Repository Portfolio category scorer.

Why this file exists
---------------------
Per the task's "Analyze" list: Repositories, Stars, Forks, Languages.
This scorer covers the breadth-of-work signals — how many original
repositories a user has, how much community engagement (stars/forks)
their work has attracted, and how diverse their language footprint is —
as opposed to the depth-of-quality signals (README content, pinned-repo
curation) that get their own dedicated scorers.

How it works
------------
Three independent 0–100 sub-signals, averaged with equal weight:
  1. **Repo count** — non-fork repos owned by the user, against
     `config.target_repo_count`. Forks are excluded because they aren't
     the user's own work; `list_repos(type="owner")` already excludes
     repos the user only contributes to, so this is specifically
     "original work the user authored".
  2. **Stars** — total stars across all non-fork repos, against
     `config.target_star_count`. Capped at 100% rather than scaling
     linearly forever, so one viral repo doesn't make every other
     category irrelevant.
  3. **Language diversity** — count of distinct primary languages across
     non-fork repos, against `config.target_language_count`.

`language_distribution` (repo count + percentage per language) is
surfaced via `details` for the API response's statistics section.

Where future code should go
----------------------------
A byte-weighted language breakdown (via the `/repos/{owner}/{repo}
/languages` endpoint) instead of the current one-language-per-repo
heuristic would slot in here — swap `_language_counts()`'s input source,
the rest of the scorer is unaffected.
"""

from app.services.github_analysis.base import SignalScorer
from app.services.github_analysis.config import GitHubAnalysisConfig
from app.services.github_analysis.types import GitHubProfileContext, RawSignalScore


def _language_counts(repos: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for repo in repos:
        if repo.is_fork or not repo.language:
            continue
        counts[repo.language] = counts.get(repo.language, 0) + 1
    return counts


class RepositoryPortfolioScorer(SignalScorer):
    """Scores repository count, star/fork engagement, and language diversity."""

    def __init__(self, config: GitHubAnalysisConfig) -> None:
        self._config = config

    def score(self, context: GitHubProfileContext) -> RawSignalScore:
        own_repos = [r for r in context.repos if not r.is_fork]
        total_stars = sum(r.stars for r in own_repos)
        total_forks = sum(r.forks for r in own_repos)
        language_counts = _language_counts(context.repos)

        repo_count_score = min(len(own_repos) / self._config.target_repo_count, 1.0) * 100
        stars_score = min(total_stars / self._config.target_star_count, 1.0) * 100
        language_score = min(len(language_counts) / self._config.target_language_count, 1.0) * 100

        score = round((repo_count_score + stars_score + language_score) / 3, 2)

        suggestions: list[str] = []
        if not own_repos:
            suggestions.append(
                "No public repositories were found. Publish some of your work — even small "
                "projects — so recruiters have something to evaluate."
            )
        elif len(own_repos) < self._config.target_repo_count:
            suggestions.append(
                f"You have {len(own_repos)} public repositories; aim for at least "
                f"{self._config.target_repo_count} to give recruiters a fuller picture of your work."
            )
        if own_repos and total_stars == 0:
            suggestions.append(
                "None of your repositories have stars yet. Share your best projects "
                "(e.g. on LinkedIn or relevant communities) to build visibility."
            )
        if own_repos and len(language_counts) < self._config.target_language_count:
            suggestions.append(
                "Your repositories show limited language diversity. If you work across "
                "multiple stacks, make sure that work is represented in public repos."
            )

        total_repo_count = len(context.repos)
        distribution = [
            {
                "language": language,
                "repo_count": count,
                "percentage": round((count / total_repo_count) * 100, 1) if total_repo_count else 0.0,
            }
            for language, count in sorted(language_counts.items(), key=lambda item: -item[1])
        ]

        return RawSignalScore(
            score=score,
            suggestions=suggestions,
            details={
                "non_fork_repo_count": len(own_repos),
                "total_stars": total_stars,
                "total_forks": total_forks,
                "language_distribution": distribution,
            },
        )
