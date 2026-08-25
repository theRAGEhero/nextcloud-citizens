# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""closing a session, frozen final report snapshot, audio deletion marker

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.add_column(sa.Column("closed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("final_report_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("final_report_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("audio_deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("audio_deleted_at")
    with op.batch_alter_table("assemblies") as batch:
        batch.drop_column("final_report_at")
        batch.drop_column("final_report_json")
        batch.drop_column("closed_at")
