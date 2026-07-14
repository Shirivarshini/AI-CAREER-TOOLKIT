"""
Section category scorer — generic wrapper around one `linkedin_heuristics` function.

Why this file exists
---------------------
Seven of the engine's eight categories (Headline, About, Experience, Skills,
Education, Projects, Certifications) score exactly the same way: take one
section's raw text, run it through the matching rule-based function already
defined in `app.utils.linkedin_heuristics` (built in the prior part of this
feature), and treat a missing/blank section as a hard 0 with a standard
"add this section" suggestion. Rather than writing seven near-identical
`CategoryScorer` subclasses that would only differ in which text/heuristic
they close over, this single reusable class is parameterized with both —
consistent with the task's "reusable scoring engine" requirement and with
not duplicating logic that `linkedin_heuristics.py` already owns and tests
(`tests/test_linkedin_heuristics.py`) independently.

How it works
------------
`_default_scorers()` in `scorer.py` constructs one `SectionCategoryScorer`
per content category, each closing over:
  - which `LinkedInProfileContext` attribute holds that section's text
    (`text_extractor`),
  - which `linkedin_heuristics.score_*` function judges it (`heuristic_fn`),
  - a human-readable label for the missing-section suggestion.

Where future code should go
----------------------------
A category whose signal isn't "one section's text -> one heuristic
function" (e.g. Completeness, which reasons across several sections at
once) needs its own dedicated `CategoryScorer` file instead — see
`completeness_scorer.py`.
"""

from collections.abc import Callable

from app.services.linkedin_analysis.base import CategoryScorer
from app.services.linkedin_analysis.types import LinkedInProfileContext, RawSignalScore
from app.utils.linkedin_heuristics import SectionHeuristicResult


class SectionCategoryScorer(CategoryScorer):
    """Scores one profile section by delegating to a `linkedin_heuristics.score_*` function."""

    def __init__(
        self,
        text_extractor: Callable[[LinkedInProfileContext], str | None],
        heuristic_fn: Callable[[str], SectionHeuristicResult],
        section_label: str,
    ) -> None:
        self._text_extractor = text_extractor
        self._heuristic_fn = heuristic_fn
        self._section_label = section_label

    def score(self, context: LinkedInProfileContext) -> RawSignalScore:
        text = self._text_extractor(context)
        if not text or not text.strip():
            return RawSignalScore(
                score=0.0,
                suggestions=[
                    f"Add a {self._section_label} section — LinkedIn's own search and "
                    "ranking both favor complete profiles."
                ],
                details={"present": False},
            )

        result = self._heuristic_fn(text)
        return RawSignalScore(
            score=result.score,
            suggestions=result.suggestions,
            details={"present": True},
        )
