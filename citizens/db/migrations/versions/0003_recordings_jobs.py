"""recorder sessions, recordings, audio chunks, app jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recorder_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "invite_id",
            sa.String(36),
            sa.ForeignKey("recorder_invites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assembly_id",
            sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recorder_sessions_invite_id", "recorder_sessions", ["invite_id"])
    op.create_index("ix_recorder_sessions_assembly_id", "recorder_sessions", ["assembly_id"])

    op.create_table(
        "recordings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "assembly_id",
            sa.String(36),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "table_id", sa.String(36), sa.ForeignKey("tables.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column(
            "recorder_session_id",
            sa.String(36),
            sa.ForeignKey("recorder_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=True),
        sa.Column("received_chunks", sa.Integer(), nullable=False),
        sa.Column("canonical_audio_path", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("assembly_id", "round_id", "table_id", "state"):
        op.create_index(f"ix_recordings_{column}", "recordings", [column])

    op.create_table(
        "audio_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recording_id",
            sa.String(36),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("recording_id", "sequence_number", name="uq_audio_chunks_recording_id"),
    )
    op.create_index("ix_audio_chunks_recording_id", "audio_chunks", ["recording_id"])

    op.create_table(
        "app_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_jobs_type", "app_jobs", ["type"])
    op.create_index("ix_app_jobs_state", "app_jobs", ["state"])
    op.create_index("ix_app_jobs_next_attempt_at", "app_jobs", ["next_attempt_at"])


def downgrade() -> None:
    for table in ("app_jobs", "audio_chunks", "recordings", "recorder_sessions"):
        op.drop_table(table)
