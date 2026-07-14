"""
Parseability category scorer.

Why this file exists
---------------------
Per the PRD (6.1): "File type / parseability." By the time scoring runs,
extraction has already succeeded (a hard failure raises `ResumeParsingError`
upstream in `resume_service.py` and scoring never runs) — so this category
isn't pass/fail. It measures *extraction confidence*: signals that the
text extraction was clean and complete versus signals of a likely
scanned/image-based PDF or a barely-extractable document, both of which
are exactly what breaks real-world ATS parsers too.

How it works
------------
Three config-driven signals:
  1. Word count too low -> likely a scanned image or near-empty document.
  2. Word count too high -> likely extraction picked up repeated/garbled
     boilerplate (rare, but worth a mild flag).
  3. Non-alphanumeric character ratio too high -> likely OCR/extraction
     artifacts rather than clean text.
Score starts at 100 and is reduced for each triggered signal.

Where future code should go
----------------------------
If future modules track extraction confidence more directly (e.g.
pdfplumber's per-character confidence, or a scanned-page detector), add
that as a new signal here — this category's role in the overall engine
does not change.
"""

import re

from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig
from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore

_ALNUM_OR_COMMON_PATTERN = re.compile(r"[A-Za-z0-9\s.,:;()/@%+#-]")

_LOW_WORD_COUNT_PENALTY = 50.0
_HIGH_WORD_COUNT_PENALTY = 10.0
_LOW_ALNUM_RATIO_PENALTY = 30.0


class ParseabilityScorer(CategoryScorer):
    """Scores confidence in the quality/completeness of the text extraction."""

    def __init__(self, config: ATSScoringConfig) -> None:
        self._config = config

    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        text = context.resume_text
        word_count = len(text.split())

        score = 100.0
        suggestions: list[str] = []

        if word_count < self._config.min_expected_word_count:
            score -= _LOW_WORD_COUNT_PENALTY
            suggestions.append(
                "Very little text could be extracted from this file. It may be a scanned "
                "image or contain most content as graphics — use a native, text-based "
                "PDF or DOCX instead."
            )
        elif word_count > self._config.max_expected_word_count:
            score -= _HIGH_WORD_COUNT_PENALTY
            suggestions.append(
                "An unusually large amount of text was extracted. Double-check the document "
                "for repeated or duplicated content, or condense the resume to 1-2 pages."
            )

        alnum_ratio = self._alnum_ratio(text)
        if alnum_ratio < self._config.min_alnum_ratio:
            score -= _LOW_ALNUM_RATIO_PENALTY
            suggestions.append(
                "The extracted text contains a high proportion of unusual characters, which "
                "often indicates extraction issues with complex formatting or embedded images."
            )

        return RawCategoryScore(
            score=round(max(score, 0.0), 2),
            suggestions=suggestions,
            details={
                "word_count": word_count,
                "alnum_ratio": round(alnum_ratio, 4),
            },
        )

    @staticmethod
    def _alnum_ratio(text: str) -> float:
        if not text:
            return 0.0
        matches = len(_ALNUM_OR_COMMON_PATTERN.findall(text))
        return matches / len(text)
