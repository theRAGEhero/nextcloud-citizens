# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""findings and evidence

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "assembly_id", sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "table_id", sa.String(36), sa.ForeignKey("tables.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "recording_id", sa.String(36),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("support", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("ai_model", sa.String(120), nullable=False),
        sa.Column("original_json", sa.Text(), nullable=False),
        sa.Column("source_finding_ids", sa.Text(), nullable=False),
        sa.Column("mentioned_table_count", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("assembly_id", "round_id", "status"):
        op.create_index(f"ix_findings_{column}", "findings", [column])

    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "finding_id", sa.String(36),
            sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "transcript_segment_id", sa.String(36),
            sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.UniqueConstraint("finding_id", "transcript_segment_id", name="uq_finding_evidence_finding_id"),
    )
    op.create_index("ix_finding_evidence_finding_id", "finding_evidence", ["finding_id"])
    op.create_index(
        "ix_finding_evidence_transcript_segment_id", "finding_evidence", ["transcript_segment_id"]
    )


def downgrade() -> None:
    op.drop_table("finding_evidence")
    op.drop_table("findings")
