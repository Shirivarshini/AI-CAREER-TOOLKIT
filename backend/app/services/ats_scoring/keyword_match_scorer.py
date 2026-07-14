"""
Keyword Match category scorer.

Why this file exists
---------------------
Per the PRD (5.1 / 6.1): "If a Job Description is pasted, missing keywords
vs. that JD are explicitly highlighted," using "JD keyword extraction
(TF-IDF or frequency-based)." This scorer implements the frequency-based
approach explicitly named in the PRD (no NLP dependency needed).

How it works
------------
Two modes, chosen automatically based on whether `context.job_description`
is present:

1. **Job description provided** (real match, per PRD): tokenize the JD,
   strip stopwords/short tokens, rank by frequency, take the top N
   (config-driven) as the target keyword set. Score = % of those keywords
   found (case-insensitive substring match) in the resume text.
   `details["missing_keywords"]` is populated — this is what the engine
   surfaces at the top level as `ATSScoringResult.missing_keywords`.

2. **No job description** (fallback, since a resume can be analyzed
   without a target role): score how many distinct skills the resume's
   Skills section actually lists, against a configurable target count
   (`config.target_skill_count`). This avoids the misleading alternative
   of guessing "generic missing keywords" with no real target to compare
   against — `missing_keywords` stays empty in this mode, matching the
   PRD's explicit "IF a JD is pasted" condition.

Where future code should go
----------------------------
If TF-IDF-based extraction (the PRD's other named option) is preferred
later for multi-word technical terms, add it as an alternate extraction
function here and select between them via a config flag — the scorer's
public interface (`score()`) does not need to change.
"""

import re

from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig
from app.services.ats_scoring.section_parser import parse_sections
from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore

_WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#-]{1,}")


def _extract_jd_keywords(job_description: str, config: ATSScoringConfig) -> list[str]:
    """Frequency-based keyword extraction from a job description (PRD-specified approach)."""
    raw_tokens = _WORD_PATTERN.findall(job_description)
    # Strip trailing punctuation picked up by the pattern's mid-token allowance
    # for '.', '+', '#', '-' (needed for terms like "C++", "C#", ".NET") — a
    # token-ending period/comma/colon from normal sentence punctuation isn't
    # part of the term itself and must not be kept.
    tokens = [t.lower().rstrip(".,;:") for t in raw_tokens]
    tokens = [t for t in tokens if len(t) >= config.min_keyword_length and t not in config.stopwords]

    frequency: dict[str, int] = {}
    for token in tokens:
        frequency[token] = frequency.get(token, 0) + 1

    ranked = sorted(frequency.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _count in ranked[: config.top_keyword_count]]


def _extract_skills_list(resume_text: str, section_synonyms: dict[str, list[str]]) -> list[str]:
    """Pull distinct comma/bullet/newline-separated entries out of the Skills section, if found."""
    sections = parse_sections(resume_text, section_synonyms)
    skills_text = sections.get("skills", "")
    if not skills_text:
        return []

    # Skills sections are typically comma-, bullet-, or newline-separated.
    raw_items = re.split(r"[,\n•·\u2022]+", skills_text)
    return [item.strip() for item in raw_items if item.strip()]


class KeywordMatchScorer(CategoryScorer):
    """Scores keyword alignment against a job description, or Skills-section richness as a fallback."""

    def __init__(self, config: ATSScoringConfig) -> None:
        self._config = config

    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        if context.job_description and context.job_description.strip():
            return self._score_against_job_description(context)
        return self._score_without_job_description(context)

    def _score_against_job_description(self, context: ATSScoringContext) -> RawCategoryScore:
        keywords = _extract_jd_keywords(context.job_description or "", self._config)
        if not keywords:
            return RawCategoryScore(
                score=100.0,
                suggestions=[],
                details={"missing_keywords": [], "matched_keywords": []},
            )

        resume_lower = context.resume_text.lower()
        matched = [kw for kw in keywords if kw in resume_lower]
        missing = [kw for kw in keywords if kw not in resume_lower]

        score = round((len(matched) / len(keywords)) * 100, 2)

        suggestions: list[str] = []
        if missing:
            preview = ", ".join(missing[:10])
            suggestions.append(
                f"Add these keywords from the job description if genuinely applicable: {preview}."
            )

        return RawCategoryScore(
            score=score,
            suggestions=suggestions,
            details={"missing_keywords": missing, "matched_keywords": matched},
        )

    def _score_without_job_description(self, context: ATSScoringContext) -> RawCategoryScore:
        skills = _extract_skills_list(context.resume_text, self._config.section_synonyms)
        target = self._config.target_skill_count

        score = round(min(len(skills) / target, 1.0) * 100, 2) if target else 100.0

        suggestions: list[str] = []
        if len(skills) < target:
            suggestions.append(
                "Paste a job description for a precise keyword-match score. In the meantime, "
                f"list more specific skills in your Skills section (found {len(skills)}, "
                f"aim for at least {target})."
            )
        elif not skills:
            suggestions.append(
                "No Skills section was detected. Add one listing your key technical and "
                "professional skills — ATS systems weigh this heavily."
            )

        # Intentionally empty: without a job description there is no real target
        # to compute "missing keywords" against (see module docstring).
        return RawCategoryScore(
            score=score,
            suggestions=suggestions,
            details={"missing_keywords": [], "detected_skill_count": len(skills)},
        )
