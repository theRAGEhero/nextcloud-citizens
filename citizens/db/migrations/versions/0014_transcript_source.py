# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""record whether a transcript came from live captions

With final transcription switched off, live captions become the assembly's
only transcript. That is a weaker record — captions can miss audio an engine
was too slow to take, and a failed session resumes after a cooldown — so the
report has to be able to say where its text came from. Existing rows are all
from the batch path, which is what the default preserves.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transcripts") as batch:
        batch.add_column(
            sa.Column("source", sa.String(10), nullable=False, server_default="final")
        )


def downgrade() -> None:
    with op.batch_alter_table("transcripts") as batch:
        batch.drop_column("source")
