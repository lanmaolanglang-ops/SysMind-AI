"""provider settings and connection-test audit

Revision ID: 0007_provider_settings
Revises: 0006_phase5a
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0007_provider_settings"
down_revision = "0006_phase5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("secret_reference", sa.String(120)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "provider_connection_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_connection_tests")
    op.drop_table("provider_settings")
