"""
ATS Scoring Engine — category scorer interface.

Why this file exists
---------------------
Each of the five scoring categories (Keyword Match, Formatting, Section
Completeness, Achievements, Parseability) is implemented as its own class
with a single responsibility, all conforming to this one interface. This
is what makes the engine open/closed (SOLID): adding a sixth category
later means writing a new `CategoryScorer` subclass and registering it in
`ATSScorer` — no existing scorer needs to change.

How it works
------------
`CategoryScorer` is a tiny ABC with one method, `score(context) ->
RawCategoryScore`. Scorers are intentionally weight-agnostic — they don't
know or care how important their category is relative to the others; the
`ATSScorer` engine applies the configured weight afterward. This keeps
each scorer independently testable (assert on the raw 0–100 score) and
keeps weighting logic in exactly one place.

Where future code should go
----------------------------
New scorers live in this same package as `<category>_scorer.py`, each
implementing this interface and taking an `ATSScoringConfig` in their
constructor for any tunables they need (never hardcoded).
"""

from abc import ABC, abstractmethod

from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore


class CategoryScorer(ABC):
    """Interface every ATS scoring category must implement."""

    @abstractmethod
    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        """Compute this category's raw 0–100 score, suggestions, and details."""
        raise NotImplementedError
