# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""transcripts, segments, words

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recording_id",
            sa.String(36),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("raw_response_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transcripts_recording_id", "transcripts", ["recording_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "transcript_id",
            sa.String(36),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(20), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("transcript_id", "sequence", name="uq_transcript_segments_transcript_id"),
    )
    op.create_index("ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"])

    op.create_table(
        "transcript_words",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "segment_id",
            sa.String(36),
            sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(200), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
    )
    op.create_index("ix_transcript_words_segment_id", "transcript_words", ["segment_id"])


def downgrade() -> None:
    for table in ("transcript_words", "transcript_segments", "transcripts"):
        op.drop_table(table)
