"""
Achievements category scorer.

Why this file exists
---------------------
Per the PRD (6.1): "Action-verb usage and quantified achievements." This
scorer measures two independent, well-established resume-quality signals:
whether bullet points open with strong action verbs ("Led", "Built",
"Reduced"...) rather than weak phrasing ("Responsible for..."), and
whether accomplishments are quantified (percentages, dollar amounts,
counts).

How it works
------------
- Action-verb ratio: fraction of content lines whose first word (after
  stripping bullet characters) is in the configured `action_verbs` set.
- Quantification ratio: fraction of content lines containing a number,
  percentage, or currency amount.
- Final score is a weighted blend of the two (60% action verbs, 40%
  quantification — action verbs are the more universally-applicable
  signal since not every line describes a measurable outcome).

Where future code should go
----------------------------
If achievement quality should later be scored per-section (e.g. only
within Experience/Projects, not Education), pass parsed sections in via
`ATSScoringContext` and restrict analysis to the relevant section text —
the ratio-based scoring approach here does not need to change.
"""

import re

from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig
from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore
from app.utils.text_quality import non_empty_lines

_QUANTIFIER_PATTERN = re.compile(r"\d+(\.\d+)?\s*%|\$\s?\d[\d,]*|\b\d[\d,]*\+?\b")
_LEADING_BULLET_PATTERN = re.compile(r"^[\W_]+")

# Relative weight between the two sub-signals within this category.
# Internal scoring policy (not a top-level category weight — see
# ATSScoringConfig.weights for those), so kept as a local constant.
_ACTION_VERB_SUBWEIGHT = 0.60
_QUANTIFICATION_SUBWEIGHT = 0.40


class AchievementsScorer(CategoryScorer):
    """Scores action-verb usage and quantified impact in resume bullet points."""

    def __init__(self, config: ATSScoringConfig) -> None:
        self._config = config

    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        lines = non_empty_lines(context.resume_text)
        if not lines:
            return RawCategoryScore(
                score=0.0,
                suggestions=["No content was found to evaluate for achievements."],
                details={"action_verb_ratio": 0.0, "quantification_ratio": 0.0},
            )

        action_verb_hits = sum(1 for line in lines if self._starts_with_action_verb(line))
        quantified_hits = sum(1 for line in lines if _QUANTIFIER_PATTERN.search(line))

        action_verb_ratio = action_verb_hits / len(lines)
        quantification_ratio = quantified_hits / len(lines)

        score = (
            action_verb_ratio * _ACTION_VERB_SUBWEIGHT
            + quantification_ratio * _QUANTIFICATION_SUBWEIGHT
        ) * 100

        suggestions: list[str] = []
        if action_verb_ratio < 0.3:
            suggestions.append(
                "Start more bullet points with strong action verbs (e.g. 'Led', 'Built', "
                "'Implemented', 'Reduced') instead of passive phrasing like 'Responsible for'."
            )
        if quantification_ratio < 0.2:
            suggestions.append(
                "Quantify more of your achievements with numbers, percentages, or dollar "
                "amounts (e.g. 'Reduced load time by 30%', 'Managed a $2M budget')."
            )

        return RawCategoryScore(
            score=round(min(score, 100.0), 2),
            suggestions=suggestions,
            details={
                "action_verb_ratio": round(action_verb_ratio, 4),
                "quantification_ratio": round(quantification_ratio, 4),
            },
        )

    def _starts_with_action_verb(self, line: str) -> bool:
        cleaned = _LEADING_BULLET_PATTERN.sub("", line).strip()
        if not cleaned:
            return False
        first_word = cleaned.split()[0].lower().strip(".,:;")
        return first_word in self._config.action_verbs
