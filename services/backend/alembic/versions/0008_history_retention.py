"""safe history deletion and retention audit

Revision ID: 0008_history_retention
Revises: 0007_provider_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0008_history_retention"
down_revision = "0007_provider_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_retention_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "data_cleanup_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True)),
        sa.Column("target_kind", sa.String(30)),
        sa.Column("target_id", sa.String(36)),
        sa.Column("deleted_scans", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_diagnoses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_log_analyses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("protected_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("data_cleanup_runs")
    op.drop_table("data_retention_policy")
