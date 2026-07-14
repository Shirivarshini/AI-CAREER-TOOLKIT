"""
Section Completeness category scorer.

Why this file exists
---------------------
Per the PRD (6.1): "Section completeness" is one of the five ATS score
sub-scores, and the resume should parse into: Contact, Summary, Skills,
Experience, Education, Projects. This scorer checks which of the
*required* sections (config-driven, not hardcoded — see
`ATSScoringConfig.required_sections`) are present and scores accordingly.

How it works
------------
- Contact is detected via regex (email/phone) over the whole document.
- All other sections are detected via `section_parser.parse_sections()`,
  which looks for short header-like lines matching configured synonyms.
- Score = (sections found / sections required) * 100.
- `details["missing_sections"]` carries the human-readable list of missing
  required sections, which the engine surfaces at the top level of
  `ATSScoringResult` per this module's explicit output requirement.

Where future code should go
----------------------------
If a "nice-to-have" (non-required) section like Projects should
contribute a smaller bonus rather than being ignored, add a
`optional_sections` field to `ATSScoringConfig` and a small bonus term
here — no other scorer needs to change.
"""

from app.services.ats_scoring.base import CategoryScorer
from app.services.ats_scoring.config import ATSScoringConfig
from app.services.ats_scoring.section_parser import detect_contact_info, parse_sections
from app.services.ats_scoring.types import ATSScoringContext, RawCategoryScore

_SECTION_DISPLAY_NAMES: dict[str, str] = {
    "contact": "Contact Information",
    "summary": "Summary / Objective",
    "skills": "Skills",
    "experience": "Experience",
    "education": "Education",
    "projects": "Projects",
}


class SectionCompletenessScorer(CategoryScorer):
    """Scores a resume on the presence of required sections."""

    def __init__(self, config: ATSScoringConfig) -> None:
        self._config = config

    def score(self, context: ATSScoringContext) -> RawCategoryScore:
        parsed_sections = parse_sections(context.resume_text, self._config.section_synonyms)
        has_contact = detect_contact_info(context.resume_text)

        present: dict[str, bool] = {"contact": has_contact}
        for section in self._config.required_sections:
            if section == "contact":
                continue
            present[section] = section in parsed_sections

        required = self._config.required_sections
        found_count = sum(1 for section in required if present.get(section, False))
        score = round((found_count / len(required)) * 100, 2) if required else 100.0

        missing_sections = [
            _SECTION_DISPLAY_NAMES.get(section, section.title())
            for section in required
            if not present.get(section, False)
        ]

        suggestions = [
            f"Add a '{name}' section — it's missing and is commonly expected by ATS parsers."
            for name in missing_sections
        ]

        return RawCategoryScore(
            score=score,
            suggestions=suggestions,
            details={
                "missing_sections": missing_sections,
                "sections_found": [s for s in required if present.get(s, False)],
            },
        )
