# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""assembly recording mode + analysis summaries

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.add_column(
            sa.Column("recording_mode", sa.String(16), nullable=False, server_default="orchestrated")
        )
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("analysis_summary", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("rounds") as batch:
        batch.add_column(sa.Column("analysis_summary", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("rounds") as batch:
        batch.drop_column("analysis_summary")
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("analysis_summary")
    with op.batch_alter_table("assemblies") as batch:
        batch.drop_column("recording_mode")
