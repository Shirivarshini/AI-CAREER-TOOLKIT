"""
Resume Analyzer — service layer (upload -> text extraction -> ATS scoring -> report storage).

Why this file exists
---------------------
The service layer holds business-process orchestration: it coordinates
validation, the storage repository, text extraction, ATS scoring, and
report persistence — without any of those concerns' implementation
details leaking into the API router. The router stays a thin HTTP
adapter; this is where the actual "recipe" for handling a resume upload
lives.

How it works
------------
`ResumeService.analyze_resume()`:
  1. Validates the filename extension.
  2. Validates the declared Content-Type / MIME type.
  3. Reads the upload into memory and validates its size.
  4. Validates the file's content signature ("magic bytes") matches its
     extension.
  5. Saves the bytes to a temporary file via `ResumeFileRepository`.
  6. Extracts text (off the event loop, via `asyncio.to_thread`, since
     pdfplumber/python-docx are blocking).
  7. Always deletes the temporary file afterward — success or failure —
     via a `finally` block, per the PRD's "delete temporary file after
     processing" requirement.
  8. Runs the extracted text through `ATSScorer` (also off the event loop,
     since regex-heavy scoring over long resume text is CPU-bound) to get
     the overall score, breakdown, suggestions, and missing sections.
  9. Builds the `ResumeAnalysisResponse`.
  10. Saves a `ResumeAnalysis` report row via `ResumeReportRepository` —
      `user_id` is whatever `app.api.deps.get_optional_current_user`
      resolved (a real user if a valid token was sent, `None` for a guest
      request). A failure here is logged and swallowed rather than raised,
      so a report-storage hiccup never turns an otherwise-successful
      analysis into a failed request for the caller.
  11. Returns the same `ResumeAnalysisResponse` from step 9, unchanged by
      whether step 10 succeeded.
"""

import asyncio
import logging
import uuid

from fastapi import Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.database import get_db
from app.repositories.report_repository import ResumeReportRepository
from app.repositories.resume_file_repository import ResumeFileRepository
from app.schemas.resume import (
    ATSScoreBreakdown,
    ATSScoreCategoryResult,
    ATSScoringResultSchema,
    ResumeAnalysisResponse,
    ResumeFileType,
)
from app.services.ats_scoring import ATSScorer, ATSScoringContext, build_ats_config_from_settings
from app.services.ats_scoring.types import ATSCategory, ATSScoringResult
from app.utils.file_validator import (
    validate_content_signature,
    validate_extension,
    validate_file_size,
    validate_mime_type,
)
from app.utils.text_extractor import extract_text

logger = logging.getLogger(__name__)


class ResumeService:
    """Orchestrates resume upload validation, text extraction, ATS scoring, cleanup, and report storage."""

    def __init__(
        self,
        file_repository: ResumeFileRepository,
        settings: Settings,
        ats_scorer: ATSScorer,
        report_repository: ResumeReportRepository,
    ) -> None:
        self._file_repository = file_repository
        self._settings = settings
        self._ats_scorer = ats_scorer
        self._report_repository = report_repository

    async def analyze_resume(
        self,
        file: UploadFile,
        job_description: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ResumeAnalysisResponse:
        """
        Validate an uploaded resume, extract its text, score it against ATS
        criteria, and return the combined result.

        `job_description` is optional (per PRD 5.1: "If a Job Description is
        pasted, missing keywords vs. that JD are explicitly highlighted") —
        when omitted, keyword matching falls back to Skills-section richness.

        Raises (via the shared AppException hierarchy, handled globally):
          - UnsupportedFileTypeError — bad extension, MIME type, or content signature
          - FileTooLargeError — empty or over the configured size limit
          - ResumeParsingError — file is valid but text extraction fails
        """
        # 1. Extension check (cheap, fails fast on obviously wrong files).
        extension = validate_extension(file.filename)

        # 2. Declared Content-Type check.
        validate_mime_type(file.content_type)

        # 3. Read the file into memory and validate its size.
        content = await file.read()
        validate_file_size(len(content), self._settings.MAX_UPLOAD_SIZE_BYTES)

        # 4. Confirm actual file content matches its claimed extension.
        validate_content_signature(content, extension)

        # 5. Persist to a temporary file (extraction libraries need a path).
        temp_path = self._file_repository.save_temp_file(content, extension)

        try:
            # 6. Extract text off the event loop (blocking I/O + CPU parsing).
            extracted_text = await asyncio.to_thread(extract_text, temp_path, extension)
        finally:
            # 7. Always clean up the temporary file, regardless of outcome.
            self._file_repository.delete_temp_file(temp_path)

        logger.info(
            "Extracted %d characters from resume '%s' (%s, %d bytes)",
            len(extracted_text),
            file.filename,
            extension,
            len(content),
        )

        # 8. Score the extracted text against ATS criteria, off the event loop
        #    (regex-heavy scoring over long text is CPU-bound).
        scoring_context = ATSScoringContext(
            resume_text=extracted_text,
            file_extension=extension,
            file_size_bytes=len(content),
            job_description=job_description,
        )
        scoring_result = await asyncio.to_thread(self._ats_scorer.score, scoring_context)

        logger.info(
            "ATS score for resume '%s': %.2f/100",
            file.filename,
            scoring_result.overall_score,
        )

        # 9. Assemble the response.
        response = ResumeAnalysisResponse(
            filename=file.filename or "unknown",
            file_type=ResumeFileType.PDF if extension == ".pdf" else ResumeFileType.DOCX,
            size_bytes=len(content),
            character_count=len(extracted_text),
            word_count=len(extracted_text.split()),
            extracted_text=extracted_text,
            ats_score=self._map_scoring_result(scoring_result),
        )

        # 10. Persist a report row for this successful analysis. Never lets a
        #     storage failure surface as a failed request (see module docstring).
        try:
            await self._report_repository.create(
                user_id=user_id,
                filename=response.filename,
                input_data={"filename": response.filename, "job_description": job_description},
                ats_score=scoring_result.overall_score,
                breakdown_json=response.ats_score.model_dump(mode="json"),
            )
        except Exception:
            logger.exception("Failed to save resume analysis report for '%s'", response.filename)

        # 11. Return the response, unaffected by whether step 10 succeeded.
        return response

    @staticmethod
    def _map_scoring_result(result: ATSScoringResult) -> ATSScoringResultSchema:
        """Map the engine's framework-agnostic dataclass onto the API's Pydantic schema."""

        def _category(name: ATSCategory) -> ATSScoreCategoryResult:
            cat_result = result.breakdown[name]
            return ATSScoreCategoryResult(
                score=cat_result.score,
                weight=cat_result.weight,
                suggestions=cat_result.suggestions,
            )

        return ATSScoringResultSchema(
            overall_score=result.overall_score,
            breakdown=ATSScoreBreakdown(
                keyword_match=_category(ATSCategory.KEYWORD_MATCH),
                formatting=_category(ATSCategory.FORMATTING),
                section_completeness=_category(ATSCategory.SECTION_COMPLETENESS),
                achievements=_category(ATSCategory.ACHIEVEMENTS),
                parseability=_category(ATSCategory.PARSEABILITY),
            ),
            suggestions=result.suggestions,
            missing_sections=result.missing_sections,
            missing_keywords=result.missing_keywords,
        )


def get_resume_service(db: AsyncSession = Depends(get_db)) -> ResumeService:
    """
    FastAPI dependency factory for ResumeService.

    The ATS scoring weights are sourced from `Settings` (env-configurable)
    via `build_ats_config_from_settings`. `db` is only used to build the
    `ResumeReportRepository` that persists each successful analysis.
    """
    settings = get_settings()
    return ResumeService(
        file_repository=ResumeFileRepository(),
        settings=settings,
        ats_scorer=ATSScorer(config=build_ats_config_from_settings(settings)),
        report_repository=ResumeReportRepository(db),
    )
