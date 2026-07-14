"""
Text-quality helper functions, shared across ATS scoring categories.

Why this file exists
---------------------
Both the Formatting and Parseability scorers need to reason about the
same underlying signals — how "clean" the extracted text looks (line
structure, garbled characters, bullet usage). Rather than duplicate this
logic in two scorer classes, the pure, stateless functions live here once
and each scorer composes them into its own score.

These are plain functions (no classes, no config objects) because they
operate purely on strings — genuinely reusable utilities, matching the
project's existing `app/utils/` convention (see `text_extractor.py`,
`file_validator.py`).

Where future code should go
----------------------------
If a new scorer needs another generic text signal (e.g. sentence-length
variance), add a function here rather than inlining it in a scorer.
"""

import re

_NON_STANDARD_CHAR_PATTERN = re.compile(r"[^\x20-\x7E\n\t\u2018\u2019\u201C\u201D\u2013\u2014•·]")


def non_empty_lines(text: str) -> list[str]:
    """Return all non-blank, stripped lines from the text."""
    return [line.strip() for line in text.split("\n") if line.strip()]


def bullet_line_ratio(lines: list[str], bullet_characters: tuple[str, ...]) -> float:
    """Fraction of lines that start with one of the given bullet characters."""
    if not lines:
        return 0.0
    bulleted = sum(1 for line in lines if line.startswith(bullet_characters))
    return bulleted / len(lines)


def average_words_per_line(lines: list[str]) -> float:
    """Average word count per non-empty line — very high values suggest collapsed columns/tables."""
    if not lines:
        return 0.0
    total_words = sum(len(line.split()) for line in lines)
    return total_words / len(lines)


def non_standard_char_ratio(text: str) -> float:
    """
    Fraction of characters that fall outside common printable ASCII/typographic
    punctuation. A high ratio suggests extraction artifacts (e.g. from a
    scanned/corrupted PDF) rather than genuine resume content.
    """
    if not text:
        return 0.0
    non_standard = len(_NON_STANDARD_CHAR_PATTERN.findall(text))
    return non_standard / len(text)
