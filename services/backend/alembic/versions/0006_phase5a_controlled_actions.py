"""phase 5a controlled current-user startup actions

Revision ID: 0006_phase5a
Revises: 0005_phase4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0006_phase5a"
down_revision = "0005_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_plans_diagnosis_id", "action_plans", ["diagnosis_id"])
    op.create_table(
        "actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("action_plans.id"), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("tool_version", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("target_name", sa.String(200), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("observed_revision", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("recovery_id", sa.String(36)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_actions_plan_id", "actions", ["plan_id"])
    op.create_index("ix_actions_diagnosis_id", "actions", ["diagnosis_id"])
    op.create_index("ix_actions_status", "actions", ["status"])
    op.create_table(
        "user_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_id", sa.String(36), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("ticket_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_confirmations_action_id", "user_confirmations", ["action_id"])
    op.create_table(
        "action_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_id", sa.String(36), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_events_action_id", "action_events", ["action_id"])
    op.create_table(
        "recovery_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id", sa.String(36), sa.ForeignKey("actions.id"), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("recovery_records")
    op.drop_index("ix_action_events_action_id", table_name="action_events")
    op.drop_table("action_events")
    op.drop_index("ix_user_confirmations_action_id", table_name="user_confirmations")
    op.drop_table("user_confirmations")
    op.drop_index("ix_actions_status", table_name="actions")
    op.drop_index("ix_actions_diagnosis_id", table_name="actions")
    op.drop_index("ix_actions_plan_id", table_name="actions")
    op.drop_table("actions")
    op.drop_index("ix_action_plans_diagnosis_id", table_name="action_plans")
    op.drop_table("action_plans")
