# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""recorder session device status columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recorder_sessions") as batch:
        batch.add_column(sa.Column("last_status_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("last_status_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recorder_sessions") as batch:
        batch.drop_column("last_status_json")
        batch.drop_column("last_status_at")
