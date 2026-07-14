"""
LinkedIn Analysis Engine — category scorer interface.

Why this file exists
---------------------
Mirrors `app.services.ats_scoring.base` / `app.services.github_analysis.base`:
each scoring category is its own object implementing one interface, keeping
the engine open/closed — a ninth category means a new `CategoryScorer`
implementation, no existing scorer changes.

How it works
------------
`CategoryScorer` is a tiny ABC with one method, `score(context) ->
RawSignalScore`. Scorers are weight-agnostic; `LinkedInProfileScorer` applies
the configured weight afterward.

Where future code should go
----------------------------
New scorers live in this package, implementing this interface. Seven of the
eight categories share one generic implementation (`SectionCategoryScorer`,
in `section_scorer.py`) since they only differ in *which* text they read and
*which* `linkedin_heuristics` function judges it — a genuinely new kind of
signal (like `completeness_scorer.py`'s cross-section logic) gets its own
file.
"""

from abc import ABC, abstractmethod

from app.services.linkedin_analysis.types import LinkedInProfileContext, RawSignalScore


class CategoryScorer(ABC):
    """Interface every LinkedIn scoring category must implement."""

    @abstractmethod
    def score(self, context: LinkedInProfileContext) -> RawSignalScore:
        """Compute this category's raw 0–100 score, suggestions, and details."""
        raise NotImplementedError
