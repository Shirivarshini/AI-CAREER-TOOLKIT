"""
ATSScorer — the ATS Scoring Engine's public entrypoint class.

Why this file exists
---------------------
This is the reusable class the task explicitly asks for: a single object
that, given resume text (and optional context like a job description),
returns a 0–100 overall score, a per-category breakdown, actionable
suggestions, and missing sections. Everything about it is configurable —
weights, thresholds, word lists — via `ATSScoringConfig`, injected at
construction time. Nothing is hardcoded inside this class.

How it works
------------
- `ATSScorer.__init__` takes an `ATSScoringConfig` (defaults provided —
  see `config.py`) and optionally a custom `scorers` mapping, so any
  individual category scorer can be swapped out or mocked (e.g. for unit
  testing the engine's aggregation logic in isolation).
- `ATSScorer.score(context)` runs every registered category scorer,
  applies each category's configured weight, computes the overall
  weighted score, and aggregates suggestions/missing-sections/
  missing-keywords into the final `ATSScoringResult`.
- Because `ATSScoringWeights` self-normalizes to sum to 1.0 (see
  `config.py`), the overall score is always a valid 0–100 value even if
  a misconfigured `.env` supplies weights that don't sum to 1.0.

Usage
-----
    from app.services.ats_scoring import ATSScorer, ATSScoringContext

    scorer = ATSScorer()  # or ATSScorer(config=ATSScoringConfig(...))
    result = scorer.score(
        ATSScoringContext(
            resume_text=extracted_text,
            file_extension=".pdf",
            file_size_bytes=123456,
            job_description=None,  # optional
        )
    )
    print(result.overall_score, result.missing_sections)

This class has no FastAPI/Pydantic/DB dependency — it can be used from a
script, a test, or a background job exactly as shown above.

Where future code should go
----------------------------
A sixth scoring category means: write a new `CategoryScorer` subclass,
add a matching weight field to `ATSScoringWeights`, and register an
instance in `_default_scorers()` below.
"""

from app.config.settings import Settings
from app.services.ats_scoring.achievements_scorer import AchievementsScorer
from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig, ATSScoringWeights
from app.services.ats_scoring.formatting_scorer import FormattingScorer
from app.services.ats_scoring.keyword_match_scorer import KeywordMatchScorer
from app.services.ats_scoring.parseability_scorer import ParseabilityScorer
from app.services.ats_scoring.section_completeness_scorer import SectionCompletenessScorer
from app.services.ats_scoring.types import (
    ATSCategory,
    ATSScoringContext,
    ATSScoringResult,
    CategoryScoreResult,
)


def build_ats_config_from_settings(settings: Settings) -> ATSScoringConfig:
    """
    Build an `ATSScoringConfig` using category weights sourced from the app's
    environment-configurable `Settings` (see `.env` / `ATS_WEIGHT_*`), while
    every other tunable (section synonyms, action verbs, thresholds, etc.)
    keeps its default from `ATSScoringConfig`.

    This is the only place that couples the framework-agnostic scoring
    engine to the FastAPI app's `Settings` — `config.py` and the scorers
    themselves have no knowledge of environment variables.
    """
    weights = ATSScoringWeights(
        keyword_match=settings.ATS_WEIGHT_KEYWORD_MATCH,
        formatting=settings.ATS_WEIGHT_FORMATTING,
        section_completeness=settings.ATS_WEIGHT_SECTION_COMPLETENESS,
        achievements=settings.ATS_WEIGHT_ACHIEVEMENTS,
        parseability=settings.ATS_WEIGHT_PARSEABILITY,
    )
    return ATSScoringConfig(weights=weights)


def _default_scorers(config: ATSScoringConfig) -> dict[ATSCategory, CategoryScorer]:
    """Build the standard set of five category scorers from the given config."""
    return {
        ATSCategory.KEYWORD_MATCH: KeywordMatchScorer(config),
        ATSCategory.FORMATTING: FormattingScorer(config),
        ATSCategory.SECTION_COMPLETENESS: SectionCompletenessScorer(config),
        ATSCategory.ACHIEVEMENTS: AchievementsScorer(config),
        ATSCategory.PARSEABILITY: ParseabilityScorer(config),
    }


class ATSScorer:
    """
    Reusable ATS scoring engine.

    Computes a 0–100 overall resume score from five weighted categories
    (Keyword Match, Formatting, Section Completeness, Achievements,
    Parseability), each independently configurable via `ATSScoringConfig`.
    """

    def __init__(
        self,
        config: ATSScoringConfig | None = None,
        scorers: dict[ATSCategory, CategoryScorer] | None = None,
    ) -> None:
        self._config = config or ATSScoringConfig()
        self._scorers = scorers or _default_scorers(self._config)

    def score(self, context: ATSScoringContext) -> ATSScoringResult:
        """Run all category scorers and aggregate into a final ATSScoringResult."""
        weights = self._config.weights
        weight_map: dict[ATSCategory, float] = {
            ATSCategory.KEYWORD_MATCH: weights.keyword_match,
            ATSCategory.FORMATTING: weights.formatting,
            ATSCategory.SECTION_COMPLETENESS: weights.section_completeness,
            ATSCategory.ACHIEVEMENTS: weights.achievements,
            ATSCategory.PARSEABILITY: weights.parseability,
        }

        breakdown: dict[ATSCategory, CategoryScoreResult] = {}
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

        return ATSScoringResult(
            overall_score=overall_score,
            breakdown=breakdown,
            suggestions=self._aggregate_suggestions(breakdown),
            missing_sections=self._extract_detail_list(
                breakdown, ATSCategory.SECTION_COMPLETENESS, "missing_sections"
            ),
            missing_keywords=self._extract_detail_list(
                breakdown, ATSCategory.KEYWORD_MATCH, "missing_keywords"
            ),
        )

    @staticmethod
    def _aggregate_suggestions(breakdown: dict[ATSCategory, CategoryScoreResult]) -> list[str]:
        """Flatten all categories' suggestions into one deduplicated, ordered list."""
        seen: set[str] = set()
        ordered: list[str] = []
        for result in breakdown.values():
            for suggestion in result.suggestions:
                if suggestion not in seen:
                    seen.add(suggestion)
                    ordered.append(suggestion)
        return ordered

    @staticmethod
    def _extract_detail_list(
        breakdown: dict[ATSCategory, CategoryScoreResult],
        category: ATSCategory,
        key: str,
    ) -> list[str]:
        result = breakdown.get(category)
        if result is None:
            return []
        value = result.details.get(key, [])
        return list(value) if isinstance(value, list) else []
