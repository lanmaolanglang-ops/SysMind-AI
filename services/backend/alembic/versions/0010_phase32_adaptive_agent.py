"""Add Phase 3.2 adaptive inputs, hypotheses, and stop reasons.

Revision ID: 0010_phase32
Revises: 0009_phase31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_phase32"
down_revision: str | None = "0009_phase31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "diagnoses",
        sa.Column("agent_round_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "diagnoses",
        sa.Column("max_agent_rounds", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "diagnoses",
        sa.Column("max_tool_calls", sa.Integer(), nullable=False, server_default="8"),
    )
    op.add_column("diagnoses", sa.Column("stop_reason", sa.String(40), nullable=True))
    op.create_table(
        "task_user_inputs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnosis_id", "sequence", name="uq_task_user_input_sequence"),
    )
    op.create_index("ix_task_user_inputs_diagnosis_id", "task_user_inputs", ["diagnosis_id"])
    op.create_table(
        "diagnosis_hypotheses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("hypothesis_key", sa.String(100), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("supporting_evidence_json", sa.Text(), nullable=False),
        sa.Column("contradicting_evidence_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnosis_id", "hypothesis_key", name="uq_diagnosis_hypothesis"),
    )
    op.create_index(
        "ix_diagnosis_hypotheses_diagnosis_id", "diagnosis_hypotheses", ["diagnosis_id"]
    )
    op.create_table(
        "agent_stop_reasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("terminal_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_stop_reasons_diagnosis_id", "agent_stop_reasons", ["diagnosis_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_stop_reasons_diagnosis_id", table_name="agent_stop_reasons")
    op.drop_table("agent_stop_reasons")
    op.drop_index("ix_diagnosis_hypotheses_diagnosis_id", table_name="diagnosis_hypotheses")
    op.drop_table("diagnosis_hypotheses")
    op.drop_index("ix_task_user_inputs_diagnosis_id", table_name="task_user_inputs")
    op.drop_table("task_user_inputs")
    op.drop_column("diagnoses", "stop_reason")
    op.drop_column("diagnoses", "max_tool_calls")
    op.drop_column("diagnoses", "max_agent_rounds")
    op.drop_column("diagnoses", "agent_round_count")
