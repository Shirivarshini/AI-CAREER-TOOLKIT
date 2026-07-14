"""
LinkedIn section heuristics — rule-based scoring, no AI/LLM.

Why this file exists
---------------------
Per the task: "Implement rule-based analysis ... Use heuristics only. No
AI API. No LLM." Each function here is a small, pure, independently
testable rule set for exactly one profile section, mirroring the
project's existing scorer style (see `app/utils/text_quality.py` for the
"plain functions operating on strings" convention, and
`app/services/ats_scoring/*_scorer.py` for the kind of signals a rule-
based resume/profile scorer looks for).

How it works
------------
Every `score_<section>()` function takes that section's raw text and
returns a `SectionHeuristicResult` (a score 0-100 plus a list of
actionable suggestions). None of these functions know about HTTP,
Pydantic schemas, or the two input methods — `LinkedInService` is the
only caller, and it maps the result onto `LinkedInSectionResult`.

Where the signals come from
----------------------------
Each heuristic follows the PRD's 6.3 checklist directly:
  - Headline: length + a value-prop separator + absence of cliché filler.
  - About: length/CTA presence, per PRD 6.3 explicitly.
  - Experience: "bullet quality" per PRD 6.3 — bullet structure, action
    verbs, quantified achievements.
  - Skills: "completeness" per PRD 6.3 — distinct skill count.
  - Education / Certifications / Projects: not explicitly detailed in the
    PRD's 6.3 prose, so these use the same spirit (completeness signals:
    dates, counts, concrete detail) applied to their own content type.

These are intentionally simple, transparent rules — not a calibrated
scoring model — consistent with "Do NOT implement overall profile
scoring yet" and "heuristics only" from the task.

Where future code should go
----------------------------
If a future module needs an overall weighted profile score, combine these
functions' `SectionHeuristicResult.score` values there (e.g. a new
`app/services/linkedin_analysis/` package mirroring `ats_scoring`) rather
than changing these functions' signatures.
"""

import re
from dataclasses import dataclass, field

from app.utils.text_quality import average_words_per_line, bullet_line_ratio, non_empty_lines

_BULLET_CHARACTERS = ("-", "*", "•", "·", "○", "▪")

_ACTION_VERBS = (
    "led", "built", "designed", "developed", "managed", "created", "launched",
    "improved", "increased", "decreased", "reduced", "implemented", "architected",
    "optimized", "delivered", "drove", "mentored", "spearheaded", "automated",
    "migrated", "scaled", "owned", "shipped",
)  # fmt: skip

_CLICHE_PHRASES = (
    "passionate", "hard worker", "hardworking", "team player", "results-driven",
    "detail-oriented", "go-getter", "self-starter", "think outside the box",
    "synergy", "thought leader",
)  # fmt: skip

_CTA_PHRASES = (
    "reach out", "let's connect", "lets connect", "feel free to contact",
    "connect with me", "dm me", "message me", "email me", "get in touch",
    "open to", "happy to chat", "always happy to",
)  # fmt: skip

_DEGREE_KEYWORDS = (
    "bachelor", "master", "b.sc", "m.sc", "bsc", "msc", "phd", "ph.d", "mba",
    "b.tech", "m.tech", "btech", "mtech", "associate", "diploma", "university",
    "college", "institute",
)  # fmt: skip

_QUANTIFIER_PATTERN = re.compile(r"\d+(\.\d+)?\s*(%|percent|x|k|m|\+)?", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)


@dataclass(frozen=True)
class SectionHeuristicResult:
    """A single section's preliminary heuristic score plus suggestions."""

    score: float
    suggestions: list[str] = field(default_factory=list)


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


def _split_items(text: str) -> list[str]:
    """Split a comma/pipe/semicolon/line/bullet-separated list into individual items."""
    normalized = re.sub(r"[•\u2022]", "\n", text)
    parts = re.split(r"[,\n;|]", normalized)
    return [item.strip() for item in parts if item.strip()]


def score_headline(text: str) -> SectionHeuristicResult:
    """
    Heuristics: overall length relative to LinkedIn's 220-character limit,
    presence of a value-proposition separator (suggesting multiple
    distinct signals rather than one generic job title), and absence of
    clichéd filler phrases.
    """
    suggestions: list[str] = []
    score = 100.0
    word_count = len(text.split())

    if len(text) < 15 or word_count < 3:
        score -= 35
        suggestions.append(
            "Headline is very short — add your role plus 2-3 specific skills or "
            "the value you bring, not just a job title."
        )
    elif len(text) < 40:
        score -= 15
        suggestions.append(
            "Headline has room to grow (LinkedIn allows up to 220 characters) — "
            "consider adding key skills or the audience/industry you serve."
        )

    if not any(separator in text for separator in ("|", "•", "-", ",")):
        score -= 15
        suggestions.append(
            "Consider separating multiple value props with a divider (e.g. "
            "'Role | Skill | Skill') instead of a single plain phrase."
        )

    lowered = text.lower()
    used_cliches = [phrase for phrase in _CLICHE_PHRASES if phrase in lowered]
    if used_cliches:
        score -= 10 * min(len(used_cliches), 2)
        suggestions.append(
            f"Replace generic filler ({', '.join(sorted(used_cliches)[:3])}) with "
            "concrete skills, technologies, or outcomes recruiters can search for."
        )

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_about(text: str) -> SectionHeuristicResult:
    """
    Heuristics: substantive length (not a one-liner, not maxed-out wall of
    text), paragraph structure, and presence of a call-to-action — per PRD
    6.3 ("About section presence/length/CTA").
    """
    suggestions: list[str] = []
    score = 100.0
    length = len(text)
    lines = non_empty_lines(text)

    if length < 150:
        score -= 30
        suggestions.append(
            "About section is quite short — aim for at least a few sentences "
            "covering your background, focus area, and what you're looking for."
        )
    elif length > 2400:
        score -= 10
        suggestions.append(
            "About section is near LinkedIn's 2,600-character limit — make sure "
            "the most important points are in the first 2-3 lines, since that's "
            "all that shows before 'see more'."
        )

    if len(lines) <= 1 and length > 300:
        score -= 15
        suggestions.append(
            "Break the About section into short paragraphs — a single dense "
            "block of text is harder to skim."
        )

    lowered = text.lower()
    if not any(phrase in lowered for phrase in _CTA_PHRASES):
        score -= 15
        suggestions.append(
            "Add a call-to-action (e.g. 'feel free to connect' or 'open to new "
            "opportunities in ...') so recruiters know you're approachable."
        )

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_experience(text: str) -> SectionHeuristicResult:
    """
    Heuristics: bullet-point structure, use of strong action verbs, and
    quantified achievements — per PRD 6.3 ("experience bullet quality").
    """
    lines = non_empty_lines(text)
    if not lines:
        return SectionHeuristicResult(score=0.0, suggestions=["Add your work experience."])

    suggestions: list[str] = []
    score = 100.0

    bullet_ratio = bullet_line_ratio(lines, _BULLET_CHARACTERS)
    if bullet_ratio < 0.3:
        score -= 20
        suggestions.append(
            "Format achievements as bullet points (one per line) rather than "
            "dense paragraphs — it's easier for recruiters to scan."
        )

    lowered = text.lower()
    action_verb_hits = sum(1 for verb in _ACTION_VERBS if re.search(rf"\b{verb}\w*", lowered))
    if action_verb_hits == 0:
        score -= 25
        suggestions.append(
            "Start bullet points with strong action verbs (e.g. 'led', 'built', "
            "'improved') instead of passive phrases like 'responsible for'."
        )

    quantified_lines = sum(1 for line in lines if _QUANTIFIER_PATTERN.search(line))
    quantified_ratio = quantified_lines / len(lines)
    if quantified_ratio < 0.2:
        score -= 25
        suggestions.append(
            "Quantify achievements with numbers where possible (e.g. '% improvement', "
            "'reduced latency by X', 'led a team of N') — this is one of the "
            "strongest recruiter signals."
        )

    if len(text) < 100:
        score -= 15
        suggestions.append("Experience section is very brief — add more detail on your key roles.")

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_education(text: str) -> SectionHeuristicResult:
    """Heuristics: degree/institution keywords present, and a graduation year present."""
    suggestions: list[str] = []
    score = 100.0
    lowered = text.lower()

    if not any(keyword in lowered for keyword in _DEGREE_KEYWORDS):
        score -= 35
        suggestions.append(
            "Include your degree type and institution name (e.g. 'B.Sc. Computer "
            "Science, XYZ University') so it's clearly recognizable."
        )

    if not _YEAR_PATTERN.search(text):
        score -= 15
        suggestions.append("Add graduation year(s) to give recruiters a clear timeline.")

    if len(text) < 20:
        score -= 15
        suggestions.append("Education section is very brief — add your field of study.")

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_skills(text: str) -> SectionHeuristicResult:
    """Heuristics: number of distinct skills listed (LinkedIn allows up to 50)."""
    suggestions: list[str] = []
    items = _split_items(text)
    count = len(items)

    if count < 5:
        score = 40.0
        suggestions.append(
            f"Only {count} skill(s) detected — LinkedIn allows up to 50 and "
            "recruiter search relies heavily on this section. Add more relevant skills."
        )
    elif count < 10:
        score = 70.0
        suggestions.append(
            f"{count} skills listed — consider adding a few more specific/technical "
            "skills to improve recruiter search visibility."
        )
    else:
        score = 100.0

    duplicate_count = len(items) - len({item.lower() for item in items})
    if duplicate_count > 0:
        score -= 10
        suggestions.append("Remove duplicate skill entries.")

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_certifications(text: str) -> SectionHeuristicResult:
    """Heuristics: number of certifications listed, and whether a year is present."""
    suggestions: list[str] = []
    items = _split_items(text)
    score = 100.0 if items else 0.0

    if len(items) == 1:
        score -= 10
        suggestions.append(
            "Only one certification listed — add any other relevant certifications "
            "or professional courses you've completed."
        )

    if not _YEAR_PATTERN.search(text):
        score -= 15
        suggestions.append("Add the year each certification was earned (or its expiry date).")

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)


def score_projects(text: str) -> SectionHeuristicResult:
    """Heuristics: number of projects listed, and presence of links or concrete detail."""
    suggestions: list[str] = []
    lines = non_empty_lines(text)
    items = _split_items(text)
    score = 100.0

    if len(items) < 2:
        score -= 25
        suggestions.append(
            "Only one project detected — add a few more to showcase range, "
            "especially ones with a visible outcome or live link."
        )

    if not _URL_PATTERN.search(text):
        score -= 15
        suggestions.append(
            "Add a link (GitHub repo, live demo, case study) for at least one "
            "project so recruiters can see it directly."
        )

    if average_words_per_line(lines) < 4:
        score -= 15
        suggestions.append(
            "Project descriptions are very brief — add a sentence on the problem, "
            "your role, and the outcome for each."
        )

    return SectionHeuristicResult(score=_clamp(score), suggestions=suggestions)
