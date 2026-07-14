"""
Top Repositories category scorer — proxy for "Pinned Repositories".

Why this file exists
---------------------
The task's "Analyze" list includes Pinned Repositories, but GitHub's
REST v3 API has no endpoint that returns a user's actual pinned
repositories — pinning is exposed only through the GraphQL v4 API's
`pinnedItems` field. Given the "Use GitHub REST API" requirement, this
scorer analyzes the closest REST-only proxy instead: the user's own
(non-fork) repositories ranked by engagement (stars, then forks), which
is a reasonable stand-in for "the repos most worth featuring" — and is
exactly the population a user *should* pin. This limitation is
deliberate and documented, not a missed requirement; see
`github_client.py`'s module docstring for the same note from the API
side.

How it works
------------
`context.top_repos` (already selected and capped at `config.
top_repos_limit` by `GitHubAnalysisService`) is scored on two signals,
averaged:
  1. **Fullness** — how close the user is to having a full "pin-worthy"
     set (`len(top_repos) / top_repos_limit`), rewarding having enough
     genuinely good repos to showcase.
  2. **Curation quality** — the fraction of those top repos that have a
     non-trivial description and a detected primary language, i.e. look
     intentionally presented rather than left with GitHub's defaults.

Where future code should go
----------------------------
If the GraphQL v4 API is ever added as a dependency, a
`GraphQLGitHubClient.get_pinned_repos()` method could feed real pinned
data into `GitHubProfileContext.top_repos` — this scorer's logic would
not need to change, only its input source.
"""

from app.services.github_analysis.base import SignalScorer
from app.services.github_analysis.config import GitHubAnalysisConfig
from app.services.github_analysis.types import GitHubProfileContext, RawSignalScore


class TopRepositoriesScorer(SignalScorer):
    """Scores the curation quality of the user's best-performing (pinned-repo-proxy) repositories."""

    def __init__(self, config: GitHubAnalysisConfig) -> None:
        self._config = config

    def score(self, context: GitHubProfileContext) -> RawSignalScore:
        top_repos = context.top_repos

        if not top_repos:
            return RawSignalScore(
                score=0.0,
                suggestions=[
                    "You have no repositories to feature yet. Once you have a few solid "
                    "projects, pin your best ones on your GitHub profile."
                ],
                details={"top_repository_names": []},
            )

        fullness_score = min(len(top_repos) / self._config.top_repos_limit, 1.0) * 100

        well_curated = [
            r
            for r in top_repos
            if r.description and len(r.description.strip()) >= self._config.min_description_length
            and r.language
        ]
        curation_score = (len(well_curated) / len(top_repos)) * 100

        score = round((fullness_score + curation_score) / 2, 2)

        suggestions: list[str] = []
        if len(top_repos) < self._config.top_repos_limit:
            suggestions.append(
                f"Pin your best {self._config.top_repos_limit} projects on your GitHub profile "
                f"so they're the first thing a recruiter sees — you currently have "
                f"{len(top_repos)} strong candidate(s) to choose from."
            )
        under_described = [
            r.name
            for r in top_repos
            if not r.description or len(r.description.strip()) < self._config.min_description_length
        ]
        if under_described:
            preview = ", ".join(under_described[:5])
            suggestions.append(f"Add a clear one-line description to: {preview}.")

        return RawSignalScore(
            score=score,
            suggestions=suggestions,
            details={"top_repository_names": [r.name for r in top_repos]},
        )
