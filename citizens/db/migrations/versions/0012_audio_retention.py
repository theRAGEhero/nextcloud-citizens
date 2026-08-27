# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""per-assembly audio retention override

NULL means "use the instance default" (the audio_retention_days setting), so
existing assemblies keep whatever the admin configures without a data fix.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.add_column(sa.Column("audio_retention_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("audio_purged_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.drop_column("audio_purged_at")
        batch.drop_column("audio_retention_days")
