"""Make the diagnosis step -> tool call link survive cascading deletes.

Revision ID: 0011_phase6_integrity
Revises: 0010_phase32

Deleting a ``diagnoses`` row cascades to both ``diagnosis_tool_calls`` and
``diagnosis_steps``.  ``diagnosis_steps.tool_call_id`` originally used NO ACTION, so if
SQLite removed the referenced tool-call rows before the steps, the delete failed with a
foreign-key error.  The link is now ``ON DELETE SET NULL``: a step keeps its own audit
data and simply loses the pointer when the tool call disappears.

SQLite cannot alter a foreign key in place, so the table is rebuilt explicitly (the
classic create/copy/drop/rename sequence) which works on every supported SQLite version.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_phase6_integrity"
down_revision: str | None = "0010_phase32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "diagnosis_steps"
_TEMP_TABLE = "diagnosis_steps_rebuilt"
_INDEX = "ix_diagnosis_steps_diagnosis_id"

_COLUMNS = (
    "id",
    "plan_id",
    "diagnosis_id",
    "sequence",
    "tool_name",
    "tool_version",
    "reason",
    "arguments_hash",
    "status",
    "tool_call_id",
    "created_at",
)


def _create_table(name: str, *, ondelete: str | None) -> None:
    tool_call_fk = (
        sa.ForeignKeyConstraint(["tool_call_id"], ["diagnosis_tool_calls.id"], ondelete=ondelete)
        if ondelete
        else sa.ForeignKeyConstraint(["tool_call_id"], ["diagnosis_tool_calls.id"])
    )
    op.create_table(
        name,
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
        tool_call_fk,
        sa.PrimaryKeyConstraint("id"),
    )


def _rebuild(*, ondelete: str | None) -> None:
    columns = ", ".join(_COLUMNS)
    _create_table(_TEMP_TABLE, ondelete=ondelete)
    op.execute(f"INSERT INTO {_TEMP_TABLE} ({columns}) SELECT {columns} FROM {_TABLE}")
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
    op.rename_table(_TEMP_TABLE, _TABLE)
    op.create_index(_INDEX, _TABLE, ["diagnosis_id"])


def upgrade() -> None:
    _rebuild(ondelete="SET NULL")
    # Record the normalized parameter hash for quick-scan tool calls too, matching the
    # event-log audit records. Nullable so pre-existing rows remain valid.
    op.add_column(
        "scan_step_events",
        sa.Column("arguments_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    # batch mode rebuilds the table, so the column drop works even on older SQLite.
    with op.batch_alter_table("scan_step_events") as batch:
        batch.drop_column("arguments_hash")
    _rebuild(ondelete=None)
