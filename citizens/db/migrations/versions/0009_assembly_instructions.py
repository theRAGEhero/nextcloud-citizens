# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""per-assembly AI analysis instructions

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.add_column(
            sa.Column("analysis_instructions", sa.Text(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.drop_column("analysis_instructions")
