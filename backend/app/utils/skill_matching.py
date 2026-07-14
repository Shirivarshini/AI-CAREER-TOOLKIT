"""
Skill-name normalization helpers, shared across the Skill-Gap Engine.

Why this file exists
---------------------
Matching a candidate's raw skill strings ("JS", "Postgres", "  Python  ")
against taxonomy skill names ("JavaScript", "PostgreSQL", "Python") needs
the same normalization logic in more than one place (matching resume
skills, matching GitHub skills, matching taxonomy requirements). These are
plain, stateless functions — no classes, no I/O — matching the project's
existing `app/utils/` convention (see `text_quality.py`, `readme_quality.
py`), so they're reusable and independently testable.

Where future code should go
----------------------------
A new generic normalization rule (e.g. stripping version numbers like
"Python 3.11" -> "python") belongs here as a function, not inlined into
the analyzer.
"""

import re

_PUNCTUATION_PATTERN = re.compile(r"[^\w.+#/ -]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_skill(raw_skill: str, skill_aliases: dict[str, str] | None = None) -> str:
    """
    Normalize a raw skill string to a canonical, comparable form:
    lowercase, trimmed, punctuation-stripped (keeping characters meaningful
    to tech skill names like '.', '+', '#', '/'), whitespace-collapsed, and
    finally passed through the alias map (e.g. "js" -> "javascript").

    Returns an empty string for blank/whitespace-only input.
    """
    if not raw_skill:
        return ""

    cleaned = _PUNCTUATION_PATTERN.sub("", raw_skill.lower().strip())
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    if not cleaned:
        return ""

    aliases = skill_aliases or {}
    return aliases.get(cleaned, cleaned)


def build_normalized_skill_index(
    skills: list[str], source: str, skill_aliases: dict[str, str] | None = None
) -> dict[str, set[str]]:
    """
    Normalize a list of raw skill strings into a `{normalized_skill: {source}}`
    index. Blank/unrecognizable entries are dropped silently (garbage input
    shouldn't crash the analysis — it just contributes nothing to matching).
    """
    index: dict[str, set[str]] = {}
    for raw in skills:
        normalized = normalize_skill(raw, skill_aliases)
        if not normalized:
            continue
        index.setdefault(normalized, set()).add(source)
    return index


def merge_skill_indexes(*indexes: dict[str, set[str]]) -> dict[str, set[str]]:
    """Merge multiple `{normalized_skill: {sources}}` indexes, unioning sources per skill."""
    merged: dict[str, set[str]] = {}
    for index in indexes:
        for skill, sources in index.items():
            merged.setdefault(skill, set()).update(sources)
    return merged
