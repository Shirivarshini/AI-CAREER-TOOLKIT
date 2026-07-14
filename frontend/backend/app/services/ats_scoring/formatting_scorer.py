"""
Formatting category scorer.

Why this file exists
---------------------
Per the PRD (6.1): formatting issues include "tables, images, columns,
non-standard fonts, headers/footers containing key info." Module 2's
extraction pipeline (pdfplumber / python-docx) produces plain text only —
it does not preserve layout, fonts, or column geometry. This scorer is
therefore explicitly a *heuristic proxy*: it infers likely formatting
problems from artifacts that show up in the extracted text itself, which
is the same constraint the PRD's own risk register acknowledges ("Resume
parsing accuracy varies by template — start with heuristic rules").

How it works
------------
Three signals, each config-driven (no magic numbers inline):
  1. Bullet usage — well-structured resumes use bullet points; very low
     bullet-line ratio suggests unstructured prose or a parsing artifact.
  2. Average words per line — abnormally high values suggest multi-column
     or table content that collapsed into single long lines during
     extraction (a classic ATS-breaking formatting issue).
  3. Non-standard character ratio — high garbled-character ratio suggests
     extraction artifacts from complex layouts, embedded images, or
     unusual fonts.
Score starts at 100 and is reduced for each triggered signal.

Where future code should go
----------------------------
If a future module re-architects extraction to preserve layout metadata
(e.g. pdfplumber's character bounding boxes, or python-docx section/table
counts), add those as new signals here — this scorer's role in the engine
does not change.
"""

from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig
from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore
from app.utils.text_quality import (
    average_words_per_line,
    bullet_line_ratio,
    non_empty_lines,
    non_standard_char_ratio,
)

# Points deducted per triggered issue. Named constants (not magic numbers
# scattered through the scoring logic), but intentionally not exposed as
# ATSScoringConfig fields — the *thresholds* that trigger them already
# are configurable; these deduction amounts are this scorer's internal
# scoring policy.
_LOW_BULLET_USAGE_PENALTY = 20.0
_LONG_LINES_PENALTY = 25.0
_NON_STANDARD_CHARS_PENALTY = 30.0


class FormattingScorer(CategoryScorer):
    """
    Heuristically scores resume formatting from extracted plain text.

    Limitation (see module docstring): without layout metadata, this
    cannot directly detect tables, images, or column count. It infers
    likely issues from text-extraction artifacts instead.
    """

    def __init__(self, config: ATSScoringConfig) -> None:
        self._config = config

    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        lines = non_empty_lines(context.resume_text)

        score = 100.0
        suggestions: list[str] = []

        bullet_ratio = bullet_line_ratio(lines, self._config.bullet_characters)
        if bullet_ratio < self._config.min_bullet_ratio:
            score -= _LOW_BULLET_USAGE_PENALTY
            suggestions.append(
                "Use bullet points for experience and skills — ATS parsers and recruiters "
                "both scan bulleted content more reliably than dense paragraphs."
            )

        avg_words = average_words_per_line(lines)
        if avg_words > self._config.max_avg_words_per_line:
            score -= _LONG_LINES_PENALTY
            suggestions.append(
                "Your resume may use multi-column layouts or tables, which can cause ATS "
                "systems to misread content out of order. Consider a single-column layout."
            )

        garbled_ratio = non_standard_char_ratio(context.resume_text)
        if garbled_ratio > self._config.max_non_standard_char_ratio:
            score -= _NON_STANDARD_CHARS_PENALTY
            suggestions.append(
                "Unusual characters were detected in the extracted text, which often comes "
                "from complex formatting, embedded images, or non-standard fonts. Consider "
                "a simpler, text-based layout."
            )

        return RawCategoryScore(
            score=round(max(score, 0.0), 2),
            suggestions=suggestions,
            details={
                "bullet_line_ratio": round(bullet_ratio, 4),
                "average_words_per_line": round(avg_words, 2),
                "non_standard_char_ratio": round(garbled_ratio, 4),
            },
        )
