"""report publishing + retrievable invite links

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assemblies") as batch:
        batch.add_column(sa.Column("report_published_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("recorder_invites") as batch:
        batch.add_column(sa.Column("token_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recorder_invites") as batch:
        batch.drop_column("token_encrypted")
    with op.batch_alter_table("assemblies") as batch:
        batch.drop_column("report_published_at")
