"""
Resume temporary file storage repository.

Why this file exists
---------------------
Clean architecture calls for isolating persistence/storage details behind
a repository, so services never touch the filesystem (or, later, S3)
directly. This repository handles writing an uploaded resume's bytes to a
temporary location and deleting it afterward — nothing else.

This is not a database repository (Module 2 has no DB persistence yet —
see PRD section 11, `ResumeAnalysis` table — that arrives once ATS scoring
needs to store results). It's a *storage* repository, which is still the
correct place for I/O concerns under clean architecture: the service layer
stays storage-agnostic and only calls `save_temp_file` / `delete_temp_file`.

How it works
------------
- Files are written under the system temp directory in an app-namespaced
  subfolder (`<tempdir>/ai_career_toolkit_resumes/`), not the persistent
  `UPLOAD_DIR` used for anything meant to survive a request — resumes are
  explicitly processed and discarded per the PRD ("Save temporarily...
  Delete temporary file after processing").
- Each file gets a UUID-based name so concurrent uploads never collide.
- All file I/O is blocking (`pathlib`/`open`), matching pdfplumber and
  python-docx which are also blocking — the service runs these via
  `asyncio.to_thread` to avoid blocking the event loop.

Where future code should go
----------------------------
When the AWS deployment (PRD section 12) is wired up, add a sibling
`S3ResumeFileRepository` implementing the same `save_temp_file` /
`delete_temp_file` interface, and swap it in via dependency injection —
the service layer will not need to change.
"""

import logging
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class ResumeFileRepository:
    """Handles writing/deleting temporary resume files on local disk."""

    def __init__(self) -> None:
        self._temp_dir = Path(tempfile.gettempdir()) / "ai_career_toolkit_resumes"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def save_temp_file(self, content: bytes, extension: str) -> Path:
        """
        Write `content` to a uniquely named temporary file and return its path.
        """
        temp_filename = f"{uuid.uuid4().hex}{extension}"
        temp_path = self._temp_dir / temp_filename

        temp_path.write_bytes(content)
        logger.debug("Saved temporary resume file: %s (%d bytes)", temp_path, len(content))
        return temp_path

    def delete_temp_file(self, path: Path) -> None:
        """
        Delete a temporary file if it exists. Never raises — cleanup failures
        are logged but must not mask the original request's success/failure.
        """
        try:
            if path.exists():
                path.unlink()
                logger.debug("Deleted temporary resume file: %s", path)
        except OSError as exc:
            logger.warning("Failed to delete temporary resume file '%s': %s", path, exc)
