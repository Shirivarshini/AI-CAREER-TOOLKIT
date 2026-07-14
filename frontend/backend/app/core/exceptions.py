"""
Custom application exception hierarchy.

Why this file exists
---------------------
Services and repositories should raise meaningful, typed exceptions
(e.g. "resume file too large", "GitHub user not found") rather than
generic `Exception` or ad-hoc `HTTPException`s scattered across business
logic. Keeping exceptions in one hierarchy lets a single middleware
(`app/middlewares/error_handler.py`) translate them into a consistent
JSON error envelope, per the PRD's API spec requirement:

    "All endpoints return standard HTTP status codes and a consistent
     JSON error envelope."

How it works
------------
`AppException` is the base class. Each subclass carries an HTTP status
code and a machine-readable `error_code`, so the frontend can branch on
`error_code` instead of parsing human-readable messages.

Where future code should go
----------------------------
Add new subclasses here as new modules need them, e.g.:
    class GitHubUserNotFoundError(AppException): ...
    class ResumeParsingError(AppException): ...
Always raise these from services/repositories — never raise raw
HTTPException outside of the API layer.
"""

from starlette import status


class AppException(Exception):
    """Base class for all application-specific exceptions."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_SERVER_ERROR"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or "An unexpected error occurred."
        super().__init__(self.message)


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ValidationError(AppException):
    """Raised when input fails business-rule validation (beyond Pydantic schema checks)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"


class UnauthorizedError(AppException):
    """Raised when authentication is missing or invalid."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class InvalidTokenError(UnauthorizedError):
    """
    Raised when a JWT fails signature verification, is missing a required
    claim (subject, jti, type), or has a claim of the wrong shape — e.g. a
    refresh token presented where an access token is expected. Distinct
    from `TokenExpiredError` so the frontend can tell "log in again" apart
    from "your session just needs a silent refresh".
    """

    error_code = "INVALID_TOKEN"


class TokenExpiredError(UnauthorizedError):
    """Raised when a JWT's signature is valid but its `exp` claim has passed."""

    error_code = "TOKEN_EXPIRED"


class TokenRevokedError(UnauthorizedError):
    """
    Raised when a JWT is otherwise well-formed and unexpired, but its `jti`
    has been recorded in the token blacklist (see
    `app/repositories/token_blacklist_repository.py`) — e.g. after logout.
    """

    error_code = "TOKEN_REVOKED"


class ConflictError(AppException):
    """Raised on unique-constraint violations (e.g. duplicate email on signup)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class FileTooLargeError(AppException):
    """Raised when an uploaded file exceeds MAX_UPLOAD_SIZE_MB."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "FILE_TOO_LARGE"


class UnsupportedFileTypeError(AppException):
    """Raised when an uploaded file's MIME type / extension isn't supported."""

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    error_code = "UNSUPPORTED_FILE_TYPE"


class ResumeParsingError(AppException):
    """
    Raised when a resume file passes upload validation (extension, MIME type,
    size, magic bytes) but its text cannot be extracted — e.g. a corrupt
    PDF/DOCX, a scanned image-only PDF with no extractable text layer, or an
    empty document.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "RESUME_PARSING_ERROR"


class ExternalServiceError(AppException):
    """
    Raised when a downstream third-party API (e.g. GitHub REST API) fails,
    times out, or returns an unexpected response.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "EXTERNAL_SERVICE_ERROR"


class RateLimitExceededError(AppException):
    """Raised when the app or a downstream API (e.g. GitHub) rate limit is hit."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"


class GitHubUserNotFoundError(NotFoundError):
    """
    Raised when the GitHub REST API returns 404 for a username — the account
    doesn't exist (or was deleted/suspended). Per PRD 5.2: "If the username
    doesn't exist ... the system returns a clear message rather than a
    generic error." A distinct `error_code` (rather than the generic
    `NOT_FOUND`) lets the frontend show a GitHub-specific message.
    """

    error_code = "GITHUB_USER_NOT_FOUND"


class TargetRoleNotFoundError(NotFoundError):
    """
    Raised when the Skill-Gap Advisor's requested `target_role` doesn't
    match any role (or alias) in the skill taxonomy. The message includes
    the list of available roles so the frontend can surface it directly
    (e.g. to power a "did you mean...?" prompt or a dropdown fallback).
    """

    error_code = "TARGET_ROLE_NOT_FOUND"


class LinkedInParsingError(AppException):
    """
    Raised when a LinkedIn PDF export passes upload validation (extension,
    MIME type, size, magic bytes) but no usable content could be recovered
    from it — either text extraction itself failed (corrupt/scanned-image
    PDF), or extraction succeeded but none of the expected LinkedIn profile
    sections (About, Experience, Education, Skills, Certifications,
    Projects) could be detected in it, suggesting the PDF isn't actually a
    LinkedIn "Save to PDF" profile export.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "LINKEDIN_PARSING_ERROR"
