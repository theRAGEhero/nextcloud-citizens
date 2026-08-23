"""assembly core: assemblies, rounds, tables, participants, assignments, recorder invites

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assemblies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expected_participants", sa.Integer(), nullable=False),
        sa.Column("default_table_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assemblies_created_by", "assemblies", ["created_by"])

    op.create_table(
        "rounds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "assembly_id",
            sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rounds_assembly_id", "rounds", ["assembly_id"])

    op.create_table(
        "tables",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("round_id", "number", name="uq_tables_round_id"),
    )
    op.create_index("ix_tables_round_id", "tables", ["round_id"])

    op.create_table(
        "participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "assembly_id",
            sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assembly_id", "label", name="uq_participants_assembly_id"),
    )
    op.create_index("ix_participants_assembly_id", "participants", ["assembly_id"])

    op.create_table(
        "table_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "table_id", sa.String(36), sa.ForeignKey("tables.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("round_id", "participant_id", name="uq_table_assignments_round_id"),
    )
    op.create_index("ix_table_assignments_round_id", "table_assignments", ["round_id"])
    op.create_index("ix_table_assignments_table_id", "table_assignments", ["table_id"])
    op.create_index("ix_table_assignments_participant_id", "table_assignments", ["participant_id"])

    op.create_table(
        "recorder_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "assembly_id",
            sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recorder_invites_assembly_id", "recorder_invites", ["assembly_id"])


def downgrade() -> None:
    for table in (
        "recorder_invites",
        "table_assignments",
        "participants",
        "tables",
        "rounds",
        "assemblies",
    ):
        op.drop_table(table)
