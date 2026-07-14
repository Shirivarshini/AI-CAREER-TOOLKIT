"""
LinkedIn PDF export — section parsing.

Why this file exists
---------------------
The PDF input path (a LinkedIn "Save to PDF" profile export) needs its
extracted plain text converted into the same structured shape
(`headline`/`about`/`experience`/`education`/`skills`/`certifications`/
`projects`/`featured`/`recommendations`) that the JSON input path
(`LinkedInProfileInput`) already provides, so `LinkedInService` can run
identical heuristics/scoring regardless of which input method was used.

How it works
------------
- Eight of the nine sections have a labeled header in LinkedIn's PDF
  export (e.g. "Summary", "Experience", "Skills", "Featured"), so they're split out
  by reusing `app.services.ats_scoring.section_parser.parse_sections` —
  the same generic, synonym-driven header-splitting engine the Resume
  Analyzer's ATS scoring already uses. `LINKEDIN_SECTION_SYNONYMS` is this
  module's own synonym map (LinkedIn's real export uses slightly
  different labels than a resume, e.g. "Licenses & Certifications").
- The headline is the exception: LinkedIn's export places it as a short,
  unlabeled line directly beneath the person's name near the top of the
  document — there's no "Headline:" header to key off of. `extract_headline`
  is a dedicated, best-effort heuristic for that case.

Limitations
-----------
Both the labeled-section split and the headline heuristic are pattern-
based, not a real PDF layout/structure parser — they assume LinkedIn's
current "Save to PDF" export conventions. An unusual export (a different
LinkedIn language locale, a redesigned export template, or a PDF that
isn't actually a LinkedIn export at all) may parse into fewer sections
than expected. `LinkedInService` treats zero detected sections as a hard
error (`LinkedInParsingError`) rather than silently returning an empty
analysis — see that file for the check.

Where future code should go
----------------------------
If LinkedIn changes its export template (or a new locale needs support),
extend `LINKEDIN_SECTION_SYNONYMS` with the new header text — no other
code here needs to change.
"""

import re

from app.services.ats_scoring.section_parser import parse_sections

# Header synonyms as they actually appear in a LinkedIn "Save to PDF"
# profile export. Deliberately distinct from `app.utils.file_validator`'s
# resume-oriented headers (e.g. LinkedIn uses "Summary" for the About
# section, and "Licenses & Certifications" rather than a bare "Certifications").
LINKEDIN_SECTION_SYNONYMS: dict[str, list[str]] = {
    "about": ["summary", "about"],
    "experience": ["experience"],
    "education": ["education"],
    "skills": ["skills", "top skills"],
    "certifications": [
        "certifications",
        "licenses & certifications",
        "licenses and certifications",
        "licenses & certification",
    ],
    "projects": ["projects", "projects & publications", "honors & awards", "honors and awards"],
    "featured": ["featured"],
    "recommendations": ["recommendations", "recommendations received"],
}

# How many of the document's leading non-empty lines to scan for a
# headline candidate. LinkedIn's export puts name -> headline -> location
# right at the top, so this only needs to cover a handful of lines.
_MAX_HEADLINE_SCAN_LINES = 8

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")


def _looks_like_headline(line: str) -> bool:
    """A real headline is short and isn't a contact detail."""
    if _EMAIL_PATTERN.search(line) or _PHONE_PATTERN.search(line):
        return False
    if len(line.split()) > 40:
        # A genuine LinkedIn headline is a short label, not a paragraph —
        # a long line this early is more likely mis-scanned body text.
        return False
    return True


def extract_headline(text: str) -> str | None:
    """
    Best-effort extraction of the profile headline from LinkedIn PDF
    export text.

    Scans the first few non-empty lines (skipping the very first, assumed
    to be the person's name) and returns the first candidate that doesn't
    look like a contact detail. Returns None if no plausible candidate is
    found in that window.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[1:_MAX_HEADLINE_SCAN_LINES]:
        if _looks_like_headline(line):
            return line
    return None


def parse_linkedin_sections(text: str) -> dict[str, str | None]:
    """
    Convert raw LinkedIn PDF export text into the structured section dict
    consumed by `LinkedInService`'s analysis step — the same shape
    (by key) as `LinkedInProfileInput`'s seven fields.

    Sections not found in the text are `None`, exactly as an omitted
    `LinkedInProfileInput` field would be.
    """
    labeled_sections = parse_sections(text, LINKEDIN_SECTION_SYNONYMS)
    return {
        "headline": extract_headline(text),
        "about": labeled_sections.get("about"),
        "experience": labeled_sections.get("experience"),
        "education": labeled_sections.get("education"),
        "skills": labeled_sections.get("skills"),
        "certifications": labeled_sections.get("certifications"),
        "projects": labeled_sections.get("projects"),
        "featured": labeled_sections.get("featured"),
        "recommendations": labeled_sections.get("recommendations"),
    }
