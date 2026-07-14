"""
Resume section parser.

Why this file exists
---------------------
Several scoring categories (Section Completeness, Achievements) need the
resume broken into named sections (Summary, Skills, Experience, Education,
Projects) rather than operating on one undifferentiated text blob. This
module owns that parsing so every scorer works from the same, consistent
section boundaries.

How it works
------------
- `parse_sections()` scans line by line. A line is treated as a section
  header if, once stripped of trailing punctuation and lowercased, it
  exactly matches one of the configured synonyms for a section AND is
  short (<=5 words) — real section headers are short labels, not sentences
  that happen to contain the word "experience".
- Everything between one recognized header and the next is that section's
  body text.
- Contact info (email/phone) is detected separately via regex over the
  *whole* document, since resumes virtually never have a literal "Contact"
  heading — the contact block just sits at the top of the page.

Where future code should go
----------------------------
If a future module needs finer-grained parsing (e.g. splitting Experience
into individual roles/bullets for structured storage), build that on top
of `parse_sections()`'s output rather than re-parsing raw text.
"""

import re

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

_MAX_HEADER_WORDS = 5


def _build_header_lookup(section_synonyms: dict[str, list[str]]) -> dict[str, str]:
    """Flatten {section: [synonym, ...]} into {synonym: section} for O(1) lookup."""
    lookup: dict[str, str] = {}
    for section_name, synonyms in section_synonyms.items():
        for synonym in synonyms:
            lookup[synonym.strip().lower()] = section_name
    return lookup


def parse_sections(text: str, section_synonyms: dict[str, list[str]]) -> dict[str, str]:
    """
    Split resume text into {section_name: body_text} based on recognized
    headers. Sections not found in the text simply won't appear as keys.
    """
    header_lookup = _build_header_lookup(section_synonyms)

    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.rstrip(":").strip().lower()
        word_count = len(normalized.split())

        if word_count <= _MAX_HEADER_WORDS and normalized in header_lookup:
            current_section = header_lookup[normalized]
            sections.setdefault(current_section, [])
            continue

        if current_section is not None:
            sections[current_section].append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items() if lines}


def detect_contact_info(text: str) -> bool:
    """Return True if an email address or phone number is found anywhere in the text."""
    return bool(EMAIL_PATTERN.search(text)) or bool(PHONE_PATTERN.search(text))
