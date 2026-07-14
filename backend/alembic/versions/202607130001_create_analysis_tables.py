"""create analysis tables

Revision ID: 202607130001
Revises: 202607120001
Create Date: 2026-07-13 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202607130001"
down_revision: Union[str, None] = "202607120001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("ats_score", sa.Float(), nullable=False),
        sa.Column("breakdown_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resume_analyses_id"), "resume_analyses", ["id"], unique=False)
    op.create_index(op.f("ix_resume_analyses_user_id"), "resume_analyses", ["user_id"], unique=False)

    op.create_table(
        "github_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(length=39), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_analyses_id"), "github_analyses", ["id"], unique=False)
    op.create_index(op.f("ix_github_analyses_user_id"), "github_analyses", ["user_id"], unique=False)
    op.create_index(op.f("ix_github_analyses_username"), "github_analyses", ["username"], unique=False)

    op.create_table(
        "linkedin_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_linkedin_analyses_id"), "linkedin_analyses", ["id"], unique=False)
    op.create_index(op.f("ix_linkedin_analyses_user_id"), "linkedin_analyses", ["user_id"], unique=False)

    op.create_table(
        "skill_gap_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_role", sa.String(length=255), nullable=False),
        sa.Column("matched_skills", postgresql.JSONB(), nullable=False),
        sa.Column("missing_skills", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_gap_results_id"), "skill_gap_results", ["id"], unique=False)
    op.create_index(op.f("ix_skill_gap_results_user_id"), "skill_gap_results", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_gap_results_user_id"), table_name="skill_gap_results")
    op.drop_index(op.f("ix_skill_gap_results_id"), table_name="skill_gap_results")
    op.drop_table("skill_gap_results")

    op.drop_index(op.f("ix_linkedin_analyses_user_id"), table_name="linkedin_analyses")
    op.drop_index(op.f("ix_linkedin_analyses_id"), table_name="linkedin_analyses")
    op.drop_table("linkedin_analyses")

    op.drop_index(op.f("ix_github_analyses_username"), table_name="github_analyses")
    op.drop_index(op.f("ix_github_analyses_user_id"), table_name="github_analyses")
    op.drop_index(op.f("ix_github_analyses_id"), table_name="github_analyses")
    op.drop_table("github_analyses")

    op.drop_index(op.f("ix_resume_analyses_user_id"), table_name="resume_analyses")
    op.drop_index(op.f("ix_resume_analyses_id"), table_name="resume_analyses")
    op.drop_table("resume_analyses")
