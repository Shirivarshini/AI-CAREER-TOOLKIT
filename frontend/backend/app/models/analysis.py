"""
Report storage models — SQLAlchemy ORM.

Why this file exists
---------------------
Backs the persistent "report" storage for every analysis type (PRD
section 11's data model: `ResumeAnalysis`, `GitHubAnalysis`,
`LinkedInAnalysis`, `SkillGapResult` — one row per completed Resume,
GitHub, LinkedIn, or Skill-Gap analysis). `ResumeService`,
`GitHubAnalysisService`, `LinkedInService`, and `SkillGapService` each
save a row here via their own repository (see
`app/repositories/report_repository.py`) right after a successful
analysis, so every result is durably recorded — this file only defines
the tables; the actual writes happen in those services.

How it works
------------
- Built on `BaseModelMixin` (UUID primary key + `created_at`, used as the
  report's timestamp) and `Base`, same as `app/models/user.py`.
- Every table stores the same six logical fields the report-storage
  requirement asks for: `user_id` (owner), `analysis_type` (a plain-string
  discriminator — "resume" / "github" / "linkedin" / "skill_gap" — kept
  even though it's implied by the table, so a row is self-describing if
  ever queried outside the ORM), `input_data` (what was analyzed —
  JSONB), the feature-specific generated result (`breakdown_json`, or
  `matched_skills`/`missing_skills` for Skill-Gap), a `score` (renamed
  `ats_score` on `ResumeAnalysis` only, for backwards compatibility with
  the existing Dashboard module), and `created_at` (the timestamp, from
  `BaseModelMixin`).
- `user_id` is nullable: every analysis route supports the PRD's guest
  mode, so a report can exist without an owning account. It's populated
  when the request carried a valid access token (see
  `app.api.deps.get_optional_current_user`), and left `None` otherwise.
- `user_id` uses `ondelete="CASCADE"` so deleting a `User` also removes
  their report history, rather than leaving orphaned rows.

Where future code should go
----------------------------
If a fifth analysis type is added, give it its own table here (following
the same six-column shape) plus a matching repository class in
`app/repositories/report_repository.py`.
"""

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseModelMixin


class ResumeAnalysis(Base, BaseModelMixin):
    """A single stored ATS scoring result (PRD 11: `ResumeAnalysis`)."""

    __tablename__ = "resume_analyses"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, default="resume")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ats_score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<ResumeAnalysis id={self.id} filename={self.filename!r} score={self.ats_score}>"


class GitHubAnalysis(Base, BaseModelMixin):
    """A single stored GitHub profile scoring result (PRD 11: `GitHubAnalysis`)."""

    __tablename__ = "github_analyses"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, default="github")
    username: Mapped[str] = mapped_column(String(39), nullable=False, index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<GitHubAnalysis id={self.id} username={self.username!r} score={self.score}>"


class LinkedInAnalysis(Base, BaseModelMixin):
    """A single stored LinkedIn profile scoring result (PRD 11: `LinkedInAnalysis`)."""

    __tablename__ = "linkedin_analyses"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, default="linkedin")
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<LinkedInAnalysis id={self.id} score={self.score}>"


class SkillGapResult(Base, BaseModelMixin):
    """A single stored skill-gap comparison result (PRD 11: `SkillGapResult`)."""

    __tablename__ = "skill_gap_results"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, default="skill_gap")
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SkillGapResult id={self.id} target_role={self.target_role!r}>"
