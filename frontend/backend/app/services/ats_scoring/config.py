"""
ATS Scoring Engine — configuration models.

Why this file exists
---------------------
The requirement is explicit: "Do not hardcode values. Allow scoring
weights to be configurable." Every tunable number or word-list used by the
scoring logic (category weights, section names/synonyms, action verbs,
stopwords, bullet characters, word-count thresholds, top-keyword count)
lives here as a named, typed, overridable field — never as a magic number
buried inside a scorer function.

How it works
------------
- `ATSScoringWeights` holds the five category weights. A `model_validator`
  normalizes them to sum to 1.0 if they don't (logging a warning), so a
  misconfigured `.env` degrades gracefully instead of silently producing
  an overall score outside 0–100.
- `ATSScoringConfig` bundles the weights with every other tunable: which
  sections are required, how to recognize them (synonyms), which verbs
  count as "action verbs", a stopword list for JD keyword extraction, etc.
  Sensible defaults are provided so `ATSScoringConfig()` works out of the
  box, but every field can be overridden — e.g. in tests, in a script, or
  from environment-derived settings (see `build_ats_config_from_settings`
  in `app/services/ats_scoring/scorer.py`).

Where future code should go
----------------------------
New tunable behavior (e.g. a per-industry action-verb list, or a
configurable list of "nice-to-have" optional sections) should be added as
a new field here with a sensible default — never as a literal inside a
scorer module.
"""

import logging

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ATSScoringWeights(BaseModel):
    """
    Relative importance of each scoring category. Must sum to 1.0 — if they
    don't (e.g. a misconfigured .env), they are automatically normalized
    and a warning is logged, rather than producing an overall score outside
    the 0–100 range.
    """

    keyword_match: float = Field(default=0.30, ge=0)
    formatting: float = Field(default=0.15, ge=0)
    section_completeness: float = Field(default=0.20, ge=0)
    achievements: float = Field(default=0.20, ge=0)
    parseability: float = Field(default=0.15, ge=0)

    @model_validator(mode="after")
    def _normalize(self) -> "ATSScoringWeights":
        total = (
            self.keyword_match
            + self.formatting
            + self.section_completeness
            + self.achievements
            + self.parseability
        )
        if total <= 0:
            raise ValueError("ATS scoring weights must sum to a positive number.")
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "ATS scoring weights sum to %.4f, not 1.0 — normalizing automatically.", total
            )
            self.keyword_match /= total
            self.formatting /= total
            self.section_completeness /= total
            self.achievements /= total
            self.parseability /= total
        return self


class ATSScoringConfig(BaseModel):
    """
    All tunable inputs to the ATS Scoring Engine. Construct with defaults
    for standard behavior, or override any field for a custom scoring
    profile (e.g. a stricter parseability threshold, or an
    industry-specific action-verb list).
    """

    weights: ATSScoringWeights = Field(default_factory=ATSScoringWeights)

    # --- Section Completeness ---
    # "contact" is detected via regex (email/phone), not a header, since
    # resumes rarely have a literal "Contact" heading — see section_parser.py.
    required_sections: list[str] = Field(
        default_factory=lambda: ["contact", "summary", "skills", "experience", "education"]
    )
    section_synonyms: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "summary": ["summary", "objective", "profile", "about me", "career objective"],
            "skills": ["skills", "technical skills", "core competencies", "key skills"],
            "experience": [
                "experience",
                "work experience",
                "employment history",
                "professional experience",
                "work history",
            ],
            "education": ["education", "academic background", "academic qualifications"],
            "projects": ["projects", "personal projects", "academic projects", "key projects"],
        }
    )

    # --- Keyword Match ---
    top_keyword_count: int = Field(default=25, gt=0, description="Top N JD keywords to match against.")
    min_keyword_length: int = Field(default=3, gt=0)
    target_skill_count: int = Field(
        default=8,
        gt=0,
        description="When no job description is provided, the number of distinct skills "
        "in the Skills section that earns a full keyword-match score.",
    )
    stopwords: set[str] = Field(default_factory=lambda: set(_DEFAULT_STOPWORDS))

    # --- Achievements ---
    action_verbs: set[str] = Field(default_factory=lambda: set(_DEFAULT_ACTION_VERBS))

    # --- Formatting ---
    bullet_characters: tuple[str, ...] = ("•", "-", "*", "·", "◦", "‣", "»")
    max_avg_words_per_line: int = Field(
        default=25, gt=0, description="Above this, lines look like collapsed multi-column/table content."
    )
    min_bullet_ratio: float = Field(
        default=0.05, ge=0, le=1, description="Minimum fraction of lines that should be bulleted."
    )
    max_non_standard_char_ratio: float = Field(default=0.02, ge=0, le=1)

    # --- Parseability ---
    min_expected_word_count: int = Field(default=150, gt=0)
    max_expected_word_count: int = Field(default=1200, gt=0)
    min_alnum_ratio: float = Field(
        default=0.85,
        ge=0,
        le=1,
        description="Minimum fraction of characters that are alphanumeric/whitespace/common "
        "punctuation before flagging likely extraction artifacts.",
    )


# Defaults are named module-level constants (not inline magic values) and
# are only ever used as the *default* for a config field above — every one
# is overridable by constructing ATSScoringConfig(action_verbs={...}, ...).
_DEFAULT_ACTION_VERBS: list[str] = [
    "achieved", "accelerated", "architected", "automated", "built", "led",
    "managed", "developed", "designed", "implemented", "created", "optimized",
    "increased", "reduced", "improved", "launched", "delivered", "drove",
    "established", "spearheaded", "streamlined", "engineered", "orchestrated",
    "mentored", "coordinated", "negotiated", "authored", "deployed",
    "migrated", "scaled", "resolved", "analyzed", "researched", "presented",
    "trained", "supervised", "directed", "initiated", "restructured",
    "generated", "executed", "transformed", "pioneered", "consolidated",
]

_DEFAULT_STOPWORDS: list[str] = [
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that",
    "the", "their", "then", "there", "these", "they", "this", "to", "was",
    "will", "with", "we", "you", "your", "our", "us", "i", "he", "she",
    "them", "his", "her", "its", "from", "have", "has", "had", "do", "does",
    "did", "can", "could", "should", "would", "may", "might", "must",
    "about", "above", "after", "again", "all", "also", "any", "because",
    "been", "before", "being", "below", "between", "both", "each", "few",
    "further", "here", "how", "more", "most", "other", "over", "own",
    "same", "so", "some", "than", "too", "under", "until", "up", "very",
    "what", "when", "where", "which", "while", "who", "whom", "why",
    "ideal", "candidate", "candidates", "hiring", "familiarity", "strong",
    "plus", "years", "join", "role", "team", "looking", "seeking", "etc",
]
