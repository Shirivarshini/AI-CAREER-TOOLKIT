"""
LinkedIn Optimizer — service layer.

Why this file exists
---------------------
Coordinates the two supported input methods (pasted JSON content, or an
uploaded LinkedIn PDF export), shared upload validation utilities,
`app.utils.linkedin_section_parser` (PDF -> structured sections), and the
`app.services.linkedin_analysis.LinkedInProfileScorer` engine (rule-based
per-section AND overall profile scoring) — without any of that leaking into
the router. All business logic for this module lives here, per the task's
"Business logic belongs only inside the Service" rule.

How it works
------------
`LinkedInService.analyze_from_json()` and `.analyze_from_pdf()` are the two
entrypoints (one per input method — see `app/api/v1/linkedin.py` for how the
router picks between them based on `Content-Type`). Both funnel into the
shared private `_analyze()`, so the engine runs identically regardless of
input method:

  1. Build a `LinkedInProfileContext` (one field per profile section, plus
     `featured`/`recommendations`) from whichever input method produced the
     raw section text.
  2. Run it through `LinkedInProfileScorer.score()` — a single call that
     returns the overall score, per-category breakdown, missing sections,
     rewrite suggestions, keyword suggestions, recruiter tips, a
     profile-strength label, and prioritized next steps (see
     `app/services/linkedin_analysis/` for how each is computed).
  3. Map that `LinkedInScoringResult` onto `LinkedInAnalysisResponse` —
     including rebuilding the legacy Part-1 `sections` dict from the same
     breakdown, so both API shapes stay in sync from one scoring pass.

`analyze_from_pdf()` mirrors `ResumeService.analyze_resume()`'s upload
flow exactly (validate extension -> validate MIME type -> read & validate
size -> validate content signature -> save to a temp file -> extract text
-> always delete the temp file in a `finally` block), reusing the very
same validation functions (`app.utils.file_validator`) and text-extraction
function (`app.utils.text_extractor.extract_text_from_pdf`) with a
PDF-only allow-list, rather than duplicating that flow. It also reuses
`ResumeFileRepository` for temp-file storage: that class already is a
generic, extension-agnostic "write bytes to a uniquely named temp file,
delete it after" repository with no resume-specific logic, so this module
does not need an equivalent of its own.

After scoring, `_analyze()` persists one `LinkedInAnalysis` report row via
`LinkedInReportRepository` — the single convergence point for both input
methods, so a report is saved exactly once per successful analysis
regardless of which path produced it. A storage failure is logged and
swallowed, never surfaced as a failed request.

Where future code should go
----------------------------
Additional input methods or scoring categories extend `_analyze()`'s
context/mapping — the report-saving step at the end should not need to
change.
"""

import asyncio
import logging
import uuid

from fastapi import Depends, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import LinkedInParsingError, ResumeParsingError
from app.repositories.report_repository import LinkedInReportRepository
from app.repositories.resume_file_repository import ResumeFileRepository
from app.schemas.linkedin import (
    LinkedInAnalysisResponse,
    LinkedInInputMethod,
    LinkedInProfileInput,
    LinkedInScoreBreakdown,
    LinkedInScoreCategoryResult,
    LinkedInSectionName,
    LinkedInSectionResult,
)
from app.services.linkedin_analysis import (
    LinkedInAnalysisConfig,
    LinkedInCategory,
    LinkedInProfileContext,
    LinkedInProfileScorer,
    LinkedInScoringResult,
    build_linkedin_config_from_settings,
)
from app.utils.file_validator import (
    validate_content_signature,
    validate_extension,
    validate_file_size,
    validate_mime_type,
)
from app.utils.linkedin_section_parser import parse_linkedin_sections
from app.utils.text_extractor import extract_text_from_pdf

logger = logging.getLogger(__name__)

# LinkedIn PDF exports only — narrower than the Resume Analyzer's
# .pdf/.docx allow-list, passed into the shared `file_validator` functions.
_ALLOWED_EXTENSIONS = {".pdf"}
_ALLOWED_MIME_TYPES = {"application/pdf"}

# Maps each of the seven core content categories to the `LinkedInSectionName`
# it corresponds to in the API's Part-1-compatible `sections` dict — the
# single source of truth for translating between the engine's own
# `LinkedInCategory` enum and the schema's `LinkedInSectionName` enum.
_CATEGORY_TO_SECTION_NAME: dict[LinkedInCategory, LinkedInSectionName] = {
    LinkedInCategory.HEADLINE: LinkedInSectionName.HEADLINE,
    LinkedInCategory.ABOUT: LinkedInSectionName.ABOUT,
    LinkedInCategory.EXPERIENCE: LinkedInSectionName.EXPERIENCE,
    LinkedInCategory.EDUCATION: LinkedInSectionName.EDUCATION,
    LinkedInCategory.SKILLS: LinkedInSectionName.SKILLS,
    LinkedInCategory.CERTIFICATIONS: LinkedInSectionName.CERTIFICATIONS,
    LinkedInCategory.PROJECTS: LinkedInSectionName.PROJECTS,
}


class LinkedInService:
    """Orchestrates LinkedIn profile input validation, PDF parsing, and scoring."""

    def __init__(
        self,
        file_repository: ResumeFileRepository,
        settings: Settings,
        scorer: LinkedInProfileScorer,
        report_repository: LinkedInReportRepository,
    ) -> None:
        self._file_repository = file_repository
        self._settings = settings
        self._scorer = scorer
        self._report_repository = report_repository

    def parse_json_payload(self, raw_body: dict) -> LinkedInProfileInput:
        """
        Validate a raw JSON request body into a `LinkedInProfileInput`.

        The router calls `request.json()` itself (rather than declaring
        `LinkedInProfileInput` as a FastAPI-bound parameter) so the same
        route can also accept a multipart PDF upload — see
        `app/api/v1/linkedin.py` for why. That means Pydantic validation
        errors surface here as a raw `pydantic.ValidationError` instead of
        FastAPI's own `RequestValidationError`; this re-raises as the
        latter so the response still goes through the existing global
        `RequestValidationError` handler and keeps the same error envelope
        shape as every other endpoint's body-validation errors.
        """
        try:
            return LinkedInProfileInput.model_validate(raw_body)
        except ValidationError as exc:
            logger.info("LinkedIn JSON body failed validation: %s", exc.errors())
            raise RequestValidationError(exc.errors()) from exc

    async def analyze_from_json(
        self, payload: LinkedInProfileInput, user_id: uuid.UUID | None = None
    ) -> LinkedInAnalysisResponse:
        """Analyze manually pasted LinkedIn profile content (the `application/json` input method)."""
        logger.info("LinkedIn analysis requested via pasted JSON content.")
        context = LinkedInProfileContext(
            headline=payload.headline,
            about=payload.about,
            experience=payload.experience,
            education=payload.education,
            skills=payload.skills,
            certifications=payload.certifications,
            projects=payload.projects,
            featured=payload.featured,
            recommendations=payload.recommendations,
        )
        return await self._analyze(context, input_method=LinkedInInputMethod.JSON, user_id=user_id)

    async def analyze_from_pdf(
        self, file: UploadFile, user_id: uuid.UUID | None = None
    ) -> LinkedInAnalysisResponse:
        """
        Analyze a LinkedIn PDF export (the `multipart/form-data` input
        method). No scraping is involved: the PDF is the user's own
        downloaded export, uploaded directly by them.

        Raises (via the shared AppException hierarchy, handled globally):
          - UnsupportedFileTypeError — not a .pdf, or content doesn't match
          - FileTooLargeError — empty or over the configured size limit
          - LinkedInParsingError — text extraction failed, or no
            recognizable LinkedIn sections were found in the extracted text
        """
        logger.info("LinkedIn analysis requested via PDF upload: '%s'", file.filename)

        # 1-4: identical validation flow to ResumeService.analyze_resume(),
        # narrowed to PDF-only via the shared file_validator functions.
        extension = validate_extension(file.filename, allowed_extensions=_ALLOWED_EXTENSIONS)
        validate_mime_type(file.content_type, allowed_mime_types=_ALLOWED_MIME_TYPES)
        content = await file.read()
        validate_file_size(len(content), self._settings.MAX_UPLOAD_SIZE_BYTES)
        validate_content_signature(content, extension)

        # 5. Persist to a temporary file (pdfplumber needs a path).
        temp_path = self._file_repository.save_temp_file(content, extension)

        try:
            # 6. Extract text off the event loop (pdfplumber is blocking).
            try:
                extracted_text = await asyncio.to_thread(extract_text_from_pdf, temp_path)
            except ResumeParsingError as exc:
                # Re-raised under this module's own error type/message so the
                # client sees a LinkedIn-specific, actionable error rather than
                # one written for the Resume Analyzer.
                raise LinkedInParsingError(
                    "Could not read the uploaded PDF. It may be corrupted, "
                    "password-protected, or a scanned image without a text layer."
                ) from exc
        finally:
            # 7. Always clean up the temporary file, regardless of outcome.
            self._file_repository.delete_temp_file(temp_path)

        logger.info(
            "Extracted %d characters from LinkedIn PDF export '%s' (%d bytes)",
            len(extracted_text),
            file.filename,
            len(content),
        )

        # 8. Convert extracted text into the same structured section shape
        #    the JSON input path already provides.
        sections_raw = parse_linkedin_sections(extracted_text)

        if not any(sections_raw.values()):
            raise LinkedInParsingError(
                "Could not detect any recognizable LinkedIn profile sections in this "
                "PDF. Make sure you uploaded a LinkedIn 'Save to PDF' profile export."
            )

        context = LinkedInProfileContext(
            headline=sections_raw.get("headline"),
            about=sections_raw.get("about"),
            experience=sections_raw.get("experience"),
            education=sections_raw.get("education"),
            skills=sections_raw.get("skills"),
            certifications=sections_raw.get("certifications"),
            projects=sections_raw.get("projects"),
            featured=sections_raw.get("featured"),
            recommendations=sections_raw.get("recommendations"),
        )
        return await self._analyze(context, input_method=LinkedInInputMethod.PDF, user_id=user_id)

    async def _analyze(
        self,
        context: LinkedInProfileContext,
        input_method: LinkedInInputMethod,
        user_id: uuid.UUID | None = None,
    ) -> LinkedInAnalysisResponse:
        """
        Run `LinkedInProfileScorer` once and map its result onto both the
        legacy Part-1 `sections` shape and Part 2's overall-score/breakdown/
        insights fields — the only place scoring actually happens, so
        `analyze_from_json`/`analyze_from_pdf` never diverge in how a
        profile is judged.
        """
        logger.info("Starting LinkedIn profile analysis (input_method=%s)", input_method.value)

        result = self._scorer.score(context)

        section_text = {
            LinkedInCategory.HEADLINE: context.headline,
            LinkedInCategory.ABOUT: context.about,
            LinkedInCategory.EXPERIENCE: context.experience,
            LinkedInCategory.EDUCATION: context.education,
            LinkedInCategory.SKILLS: context.skills,
            LinkedInCategory.CERTIFICATIONS: context.certifications,
            LinkedInCategory.PROJECTS: context.projects,
        }

        sections: dict[LinkedInSectionName, LinkedInSectionResult] = {}
        for category, section_name in _CATEGORY_TO_SECTION_NAME.items():
            category_result = result.breakdown[category]
            sections[section_name] = LinkedInSectionResult(
                content=section_text[category],
                present=category_result.present,
                score=category_result.score if category_result.present else None,
                suggestions=category_result.suggestions,
            )

        missing_sections = [_CATEGORY_TO_SECTION_NAME[category] for category in result.missing_sections]
        rewrite_suggestions = {
            _CATEGORY_TO_SECTION_NAME[category]: suggestions
            for category, suggestions in result.rewrite_suggestions.items()
        }
        breakdown = self._build_breakdown_schema(result)

        logger.info(
            "LinkedIn analysis complete: overall_score=%.2f (%s), %d/%d sections present "
            "(input_method=%s)",
            result.overall_score,
            result.profile_strength,
            len(_CATEGORY_TO_SECTION_NAME) - len(missing_sections),
            len(_CATEGORY_TO_SECTION_NAME),
            input_method.value,
        )

        response = LinkedInAnalysisResponse(
            input_method=input_method,
            sections=sections,
            missing_sections=missing_sections,
            overall_score=result.overall_score,
            breakdown=breakdown,
            rewrite_suggestions=rewrite_suggestions,
            keyword_suggestions=result.keyword_suggestions,
            recruiter_tips=result.recruiter_tips,
            profile_strength=result.profile_strength,
            next_steps=result.next_steps,
        )

        # Persist a report row for this successful analysis. Never lets a
        # storage failure surface as a failed request.
        try:
            await self._report_repository.create(
                user_id=user_id,
                input_data={
                    "input_method": input_method.value,
                    "sections": {name.value: text for name, text in section_text.items() if text},
                },
                score=result.overall_score,
                breakdown_json=response.model_dump(mode="json"),
            )
        except Exception:
            logger.exception("Failed to save LinkedIn analysis report (input_method=%s)", input_method.value)

        return response

    @staticmethod
    def _build_breakdown_schema(result: LinkedInScoringResult) -> LinkedInScoreBreakdown:
        def _category(name: LinkedInCategory) -> LinkedInScoreCategoryResult:
            cat = result.breakdown[name]
            return LinkedInScoreCategoryResult(score=cat.score, weight=cat.weight, suggestions=cat.suggestions)

        return LinkedInScoreBreakdown(
            headline=_category(LinkedInCategory.HEADLINE),
            about=_category(LinkedInCategory.ABOUT),
            experience=_category(LinkedInCategory.EXPERIENCE),
            skills=_category(LinkedInCategory.SKILLS),
            education=_category(LinkedInCategory.EDUCATION),
            projects=_category(LinkedInCategory.PROJECTS),
            certifications=_category(LinkedInCategory.CERTIFICATIONS),
            completeness=_category(LinkedInCategory.COMPLETENESS),
        )


def get_linkedin_service(
    settings: Settings = Depends(get_settings), db: AsyncSession = Depends(get_db)
) -> LinkedInService:
    """
    FastAPI dependency factory for LinkedInService.

    Wires up the shared temp-file repository, settings, the
    `LinkedInProfileScorer` engine (configured from `Settings` via
    `build_linkedin_config_from_settings`), and the `LinkedInReportRepository`
    that persists each successful analysis.
    """
    config: LinkedInAnalysisConfig = build_linkedin_config_from_settings(settings)
    return LinkedInService(
        file_repository=ResumeFileRepository(),
        settings=settings,
        scorer=LinkedInProfileScorer(config=config),
        report_repository=LinkedInReportRepository(db),
    )
