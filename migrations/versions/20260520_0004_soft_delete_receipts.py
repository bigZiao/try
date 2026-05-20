"""soft delete receipts

Revision ID: 20260520_0004
Revises: 20260520_0003
Create Date: 2026-05-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260520_0004"
down_revision: str | None = "20260520_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_receipts_deleted_at"), "receipts", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receipts_deleted_at"), table_name="receipts")
    op.drop_column("receipts", "deleted_at")
