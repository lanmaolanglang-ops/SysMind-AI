"""Add Phase 4 diagnoses, evidence calls, reports, and feedback.

Revision ID: 0005_phase4
Revises: 0004_phase3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_phase4"
down_revision: str | None = "0004_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("user_question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnoses_status", "diagnoses", ["status"])
    op.create_index("ix_diagnoses_category", "diagnoses", ["category"])
    op.create_index("ix_diagnoses_created_at", "diagnoses", ["created_at"])
    op.create_table(
        "diagnosis_tool_calls",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("tool_version", sa.String(20), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_tool_calls_diagnosis_id", "diagnosis_tool_calls", ["diagnosis_id"]
    )
    op.create_table(
        "diagnosis_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnosis_feedback_diagnosis_id", "diagnosis_feedback", ["diagnosis_id"])
    op.create_table(
        "diagnosis_model_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_hash", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_model_calls_diagnosis_id",
        "diagnosis_model_calls",
        ["diagnosis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_model_calls_diagnosis_id", table_name="diagnosis_model_calls")
    op.drop_table("diagnosis_model_calls")
    op.drop_index("ix_diagnosis_feedback_diagnosis_id", table_name="diagnosis_feedback")
    op.drop_table("diagnosis_feedback")
    op.drop_index("ix_diagnosis_tool_calls_diagnosis_id", table_name="diagnosis_tool_calls")
    op.drop_table("diagnosis_tool_calls")
    op.drop_index("ix_diagnoses_created_at", table_name="diagnoses")
    op.drop_index("ix_diagnoses_category", table_name="diagnoses")
    op.drop_index("ix_diagnoses_status", table_name="diagnoses")
    op.drop_table("diagnoses")
