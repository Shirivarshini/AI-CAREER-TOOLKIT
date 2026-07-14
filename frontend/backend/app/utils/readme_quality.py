"""
README-quality helper functions.

Why this file exists
---------------------
`ReadmeQualityScorer` needs several independent signals out of a README's
raw markdown text (length, heading structure, code examples, "how to use
this" sections, images/badges). These are plain, stateless functions —
no classes, no config objects — matching the project's existing
`app/utils/` convention (see `text_quality.py`), so they're testable in
isolation and reusable if another module ever needs to reason about
markdown quality (e.g. a future portfolio/README generator feature).

Where future code should go
----------------------------
A new generic markdown/text signal needed by a scorer belongs here as a
function, not inlined into the scorer itself.
"""

import re

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_CODE_BLOCK_PATTERN = re.compile(r"```")
_IMAGE_OR_BADGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\([^)]+\)")


def word_count(text: str) -> int:
    """Whitespace-separated word count of the README text."""
    return len(text.split())


def has_headings(text: str) -> bool:
    """Whether the README uses at least one markdown heading (`#`..`######`)."""
    return bool(_HEADING_PATTERN.search(text))

def heading_count(text: str) -> int:
    """Number of markdown headings found — a proxy for how well-structured the README is."""
    return len(_HEADING_PATTERN.findall(text))


def has_code_block(text: str) -> bool:
    """Whether the README contains at least one fenced code block (```...```)."""
    return len(_CODE_BLOCK_PATTERN.findall(text)) >= 2  # opening + closing fence


def has_image_or_badge(text: str) -> bool:
    """Whether the README embeds at least one image or badge (`![alt](url)`)."""
    return bool(_IMAGE_OR_BADGE_PATTERN.search(text))


def has_link(text: str) -> bool:
    """Whether the README contains at least one markdown link (excluding images)."""
    return bool(_LINK_PATTERN.search(text))


def contains_any_section(text: str, signal_sections: tuple[str, ...]) -> bool:
    """Whether the README mentions any of the given section keywords (e.g. 'usage', 'install')."""
    lowered = text.lower()
    return any(section in lowered for section in signal_sections)
