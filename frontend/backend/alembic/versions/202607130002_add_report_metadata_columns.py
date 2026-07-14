"""add report metadata columns

Revision ID: 202607130002
Revises: 202607130001
Create Date: 2026-07-13 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202607130002"
down_revision: Union[str, None] = "202607130001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EMPTY_JSON_OBJECT = sa.text("'{}'::jsonb")


def upgrade() -> None:
    # --- resume_analyses ---------------------------------------------------
    op.add_column(
        "resume_analyses",
        sa.Column("analysis_type", sa.String(length=50), nullable=False, server_default="resume"),
    )
    op.add_column(
        "resume_analyses",
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSON_OBJECT),
    )

    # --- github_analyses -----------------------------------------------------
    op.add_column(
        "github_analyses",
        sa.Column("analysis_type", sa.String(length=50), nullable=False, server_default="github"),
    )
    op.add_column(
        "github_analyses",
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSON_OBJECT),
    )

    # --- linkedin_analyses ---------------------------------------------------
    op.add_column(
        "linkedin_analyses",
        sa.Column("analysis_type", sa.String(length=50), nullable=False, server_default="linkedin"),
    )
    op.add_column(
        "linkedin_analyses",
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSON_OBJECT),
    )

    # --- skill_gap_results ---------------------------------------------------
    op.add_column(
        "skill_gap_results",
        sa.Column("analysis_type", sa.String(length=50), nullable=False, server_default="skill_gap"),
    )
    op.add_column(
        "skill_gap_results",
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSON_OBJECT),
    )
    # SkillGapResult had no single "score" column before (its result is a
    # matched/missing skill list, not one score) — added now so every report
    # table has the same six-field shape (PRD: "Score" on every report type).
    # Backfilled to 0 for any pre-existing rows; new rows always set the real
    # match percentage explicitly.
    op.add_column(
        "skill_gap_results",
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("skill_gap_results", "score")
    op.drop_column("skill_gap_results", "input_data")
    op.drop_column("skill_gap_results", "analysis_type")

    op.drop_column("linkedin_analyses", "input_data")
    op.drop_column("linkedin_analyses", "analysis_type")

    op.drop_column("github_analyses", "input_data")
    op.drop_column("github_analyses", "analysis_type")

    op.drop_column("resume_analyses", "input_data")
    op.drop_column("resume_analyses", "analysis_type")
