"""
Contribution Activity category scorer.

Why this file exists
---------------------
Per the task's "Analyze" list: Contribution activity. GitHub's REST API
has no full contribution-history endpoint (see `github_client.py`'s
module docstring), so this scorer works from `/users/{username}/events
/public` — GitHub's own ~90-day recent-activity window — treating
"number of distinct days with at least one public event" as the activity
signal: it rewards consistency over raw event volume (a single day with
50 commits shouldn't outscore ten separate days of steady work).

How it works
------------
`context.recent_active_dates` (deduplicated dates, already extracted by
`GitHubAnalysisService` from the raw events list) is compared against
`config.target_active_days` within `config.activity_lookback_days`.
Score is a simple ratio, capped at 100%.

Where future code should go
----------------------------
If the GraphQL v4 API is ever added (see `top_repos_scorer.py`'s note),
`contributionsCollection` would give a true full-year contribution graph
and could replace `recent_active_dates` as this scorer's input without
changing its scoring logic.
"""

from app.services.github_analysis.base import SignalScorer
from app.services.github_analysis.config import GitHubAnalysisConfig
from app.services.github_analysis.types import GitHubProfileContext, RawSignalScore


class ActivityScorer(SignalScorer):
    """Scores recent public-activity consistency (distinct active days in the lookback window)."""

    def __init__(self, config: GitHubAnalysisConfig) -> None:
        self._config = config

    def score(self, context: GitHubProfileContext) -> RawSignalScore:
        active_days = len(context.recent_active_dates)
        score = round(min(active_days / self._config.target_active_days, 1.0) * 100, 2)

        suggestions: list[str] = []
        if active_days == 0:
            suggestions.append(
                f"No public activity was found in the last {context.activity_lookback_days} days. "
                "Regular commits, even small ones, signal an active, engaged developer to recruiters."
            )
        elif active_days < self._config.target_active_days:
            suggestions.append(
                f"You had public activity on {active_days} of the last "
                f"{context.activity_lookback_days} days. Aim for more consistent contributions "
                "rather than infrequent large bursts."
            )

        return RawSignalScore(
            score=score,
            suggestions=suggestions,
            details={"active_days": active_days},
        )
