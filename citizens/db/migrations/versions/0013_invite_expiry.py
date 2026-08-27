# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""give recorder invites an expiry

A QR code is a secret printed on a poster in a public room. Without an expiry
it stayed valid indefinitely, so a photograph taken at the event still joined
the assembly months later. NULL means "never expires", which is what existing
invites keep — they were issued under the old rule.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recorder_invites") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recorder_invites") as batch:
        batch.drop_column("expires_at")
