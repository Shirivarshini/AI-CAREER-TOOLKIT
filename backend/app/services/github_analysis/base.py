"""
GitHub Analysis Engine — category scorer interface.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.base`: each scoring category is its own
class implementing one interface, keeping the engine open/closed — a
fifth category means a new `SignalScorer` subclass, no existing scorer
changes.

How it works
------------
`SignalScorer` is a tiny ABC with one method, `score(context) ->
RawSignalScore`. Scorers are weight-agnostic; `GitHubProfileScorer`
applies the configured weight afterward.

Where future code should go
----------------------------
New scorers live in this package as `<category>_scorer.py`, implementing
this interface and taking a `GitHubAnalysisConfig` in their constructor
for any tunables they need.
"""

from abc import ABC, abstractmethod

from app.services.github_analysis.types import GitHubProfileContext, RawSignalScore


class SignalScorer(ABC):
    """Interface every GitHub scoring category must implement."""

    @abstractmethod
    def score(self, context: GitHubProfileContext) -> RawSignalScore:
        """Compute this category's raw 0–100 score, suggestions, and details."""
        raise NotImplementedError
