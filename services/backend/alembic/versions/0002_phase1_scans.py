"""Add Phase 1 quick scan persistence and tool audit events.

Revision ID: 0002_phase1
Revises: 0001_phase0
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_phase1"
down_revision: str | None = "0001_phase0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("failures_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_scans_status", "system_scans", ["status"])
    op.create_index("ix_system_scans_started_at", "system_scans", ["started_at"])
    op.create_table(
        "scan_step_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("tool_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["system_scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_step_events_scan_id", "scan_step_events", ["scan_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_step_events_scan_id", table_name="scan_step_events")
    op.drop_table("scan_step_events")
    op.drop_index("ix_system_scans_started_at", table_name="system_scans")
    op.drop_index("ix_system_scans_status", table_name="system_scans")
    op.drop_table("system_scans")
