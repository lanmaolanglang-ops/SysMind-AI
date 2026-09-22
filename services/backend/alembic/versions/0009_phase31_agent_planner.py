"""Add Phase 3.1 diagnosis plans, steps, and auditable decisions.

Revision ID: 0009_phase31
Revises: 0008_history_retention
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_phase31"
down_revision: str | None = "0008_history_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("diagnoses", sa.Column("plan_confidence", sa.Float(), nullable=True))
    op.add_column("diagnoses", sa.Column("planner_status", sa.String(30), nullable=True))
    op.add_column("diagnoses", sa.Column("clarification_question", sa.Text(), nullable=True))
    op.create_table(
        "agent_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("problem_category", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnosis_id", "revision", name="uq_agent_plan_revision"),
    )
    op.create_index("ix_agent_plans_diagnosis_id", "agent_plans", ["diagnosis_id"])
    op.create_table(
        "diagnosis_steps",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("tool_version", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("tool_call_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["diagnosis_tool_calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnosis_steps_diagnosis_id", "diagnosis_steps", ["diagnosis_id"])
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=True),
        sa.Column("decision_type", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_decisions_diagnosis_id", "agent_decisions", ["diagnosis_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_decisions_diagnosis_id", table_name="agent_decisions")
    op.drop_table("agent_decisions")
    op.drop_index("ix_diagnosis_steps_diagnosis_id", table_name="diagnosis_steps")
    op.drop_table("diagnosis_steps")
    op.drop_index("ix_agent_plans_diagnosis_id", table_name="agent_plans")
    op.drop_table("agent_plans")
    op.drop_column("diagnoses", "clarification_question")
    op.drop_column("diagnoses", "planner_status")
    op.drop_column("diagnoses", "plan_confidence")
