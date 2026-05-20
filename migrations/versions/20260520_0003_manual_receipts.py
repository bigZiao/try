"""manual receipts

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-05-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260520_0003"
down_revision: str | None = "20260520_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("source_type", sa.String(length=30), nullable=False, server_default="image"))
    op.create_index(op.f("ix_receipts_source_type"), "receipts", ["source_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receipts_source_type"), table_name="receipts")
    op.drop_column("receipts", "source_type")
