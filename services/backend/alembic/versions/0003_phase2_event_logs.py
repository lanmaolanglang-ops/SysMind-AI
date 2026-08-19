"""Add Phase 2 bounded event log analysis and audit records.

Revision ID: 0003_phase2
Revises: 0002_phase1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_phase2"
down_revision: str | None = "0002_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_log_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("query_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("failures_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_log_analyses_status", "event_log_analyses", ["status"])
    op.create_index("ix_event_log_analyses_started_at", "event_log_analyses", ["started_at"])
    op.create_table(
        "event_log_step_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("tool_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("result_summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["event_log_analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_log_step_events_analysis_id", "event_log_step_events", ["analysis_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_log_step_events_analysis_id", table_name="event_log_step_events")
    op.drop_table("event_log_step_events")
    op.drop_index("ix_event_log_analyses_started_at", table_name="event_log_analyses")
    op.drop_index("ix_event_log_analyses_status", table_name="event_log_analyses")
    op.drop_table("event_log_analyses")
