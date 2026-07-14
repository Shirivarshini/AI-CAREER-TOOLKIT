"""
Upload validation helpers — extension, declared MIME type, size, and
content "magic bytes" sniffing.

Why this file exists
---------------------
The PRD requires (section 5.1 / 8): validated file type, a 5MB size cap,
and a "clear, actionable error message — not a silent failure" for
unsupported or corrupt files. Rather than scattering these checks inside
the router or service, we centralize them as small, pure, independently
testable functions here. Any future upload feature (e.g. a LinkedIn PDF
export in the LinkedIn Optimizer module) can reuse these same helpers.

How it works
------------
Three independent checks, each raising a specific `AppException` subclass
so the global error handler returns the right HTTP status + error_code:
  - `validate_extension`   -> UnsupportedFileTypeError (415)
  - `validate_mime_type`   -> UnsupportedFileTypeError (415)
  - `validate_file_size`   -> FileTooLargeError (413)
  - `validate_content_signature` -> UnsupportedFileTypeError (415)

`validate_content_signature` checks the file's actual byte signature
("magic bytes") against what its extension claims. This guards against a
malicious or mislabeled file (e.g. a renamed .exe with a .pdf extension)
passing validation purely because of its filename/header, without adding
a third-party sniffing dependency.

`validate_extension` and `validate_mime_type` accept an optional
`allowed_extensions` / `allowed_mime_types` override (defaulting to the
Resume Analyzer's .pdf/.docx allow-lists below). The LinkedIn Optimizer
module (`app/services/linkedin_service.py`), which only accepts .pdf,
passes its own narrower sets — the validation logic and error types stay
shared rather than being duplicated per module.

Where future code should go
----------------------------
If a new supported resume format is added later, extend
`ALLOWED_EXTENSIONS`, `ALLOWED_MIME_TYPES`, and `FILE_SIGNATURES` together
— all three must stay in sync for validation to work correctly. A new
module with its own allow-list does not need to touch this file at all —
it just passes its own set(s) into `validate_extension`/`validate_mime_type`.
"""

from pathlib import Path

from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError

# Extensions accepted for resume uploads, per PRD 5.1 ("PDF or DOCX").
ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx"}

# MIME types accepted, matched against the client-declared Content-Type.
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Known byte signatures ("magic numbers") for each supported extension.
# PDF files start with "%PDF". DOCX files are ZIP archives, which start
# with the local file header signature "PK\x03\x04".
FILE_SIGNATURES: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
}


def validate_extension(filename: str | None, allowed_extensions: set[str] | None = None) -> str:
    """
    Validate the uploaded file has a supported extension.

    `allowed_extensions` defaults to `ALLOWED_EXTENSIONS` (.pdf/.docx, for
    the Resume Analyzer). Other modules with a narrower allow-list (e.g.
    the LinkedIn Optimizer, which only accepts .pdf) pass their own set —
    the underlying check and error type are shared.

    Returns the lowercased extension (e.g. ".pdf") on success.
    Raises UnsupportedFileTypeError if missing or unsupported.
    """
    allowed = allowed_extensions if allowed_extensions is not None else ALLOWED_EXTENSIONS

    if not filename or "." not in filename:
        raise UnsupportedFileTypeError(
            f"No filename or file extension provided. Please upload a "
            f"{' or '.join(sorted(allowed))} file."
        )

    extension = Path(filename).suffix.lower()
    if extension not in allowed:
        raise UnsupportedFileTypeError(
            f"Unsupported file extension '{extension}'. Only "
            f"{' and '.join(sorted(allowed))} are supported."
        )
    return extension


def validate_mime_type(content_type: str | None, allowed_mime_types: set[str] | None = None) -> None:
    """
    Validate the client-declared Content-Type header.

    `allowed_mime_types` defaults to `ALLOWED_MIME_TYPES` (PDF/DOCX, for
    the Resume Analyzer) — see `validate_extension` for the same pattern.

    Raises UnsupportedFileTypeError if missing or not an allowed MIME type.
    """
    allowed = allowed_mime_types if allowed_mime_types is not None else ALLOWED_MIME_TYPES

    if not content_type or content_type not in allowed:
        raise UnsupportedFileTypeError(
            f"Unsupported content type '{content_type}'. "
            f"Only {' and '.join(sorted(allowed))} are supported."
        )


def validate_file_size(size_bytes: int, max_bytes: int) -> None:
    """
    Validate the file does not exceed the configured maximum upload size.

    Raises FileTooLargeError if the file is empty or too large.
    """
    if size_bytes <= 0:
        raise FileTooLargeError("The uploaded file is empty.")

    if size_bytes > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        raise FileTooLargeError(
            f"File is too large ({actual_mb:.2f}MB). Maximum allowed size is {max_mb:.0f}MB."
        )


def validate_content_signature(content: bytes, extension: str) -> None:
    """
    Validate that the file's actual content matches the byte signature
    expected for its extension, to catch mislabeled or corrupted uploads
    early — before spending time saving to disk and attempting extraction.

    Raises UnsupportedFileTypeError if the signature does not match.
    """
    expected_signature = FILE_SIGNATURES.get(extension)
    if expected_signature is None:
        # Should be unreachable if validate_extension() ran first, but
        # fail closed rather than silently skipping the check.
        raise UnsupportedFileTypeError(f"No known content signature for extension '{extension}'.")

    if not content.startswith(expected_signature):
        raise UnsupportedFileTypeError(
            "The file's content does not match its extension. "
            "The file may be corrupted or mislabeled."
        )
