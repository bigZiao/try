"""initial schema

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260520_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("openid", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=False)

    op.create_table(
        "receipt_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipt_batches_id"), "receipt_batches", ["id"], unique=False)
    op.create_index(op.f("ix_receipt_batches_status"), "receipt_batches", ["status"], unique=False)
    op.create_index(op.f("ix_receipt_batches_user_id"), "receipt_batches", ["user_id"], unique=False)

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("duplicate_of_receipt_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_status", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("ocr_json", sa.JSON(), nullable=True),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.Column("corrected_json", sa.JSON(), nullable=True),
        sa.Column("final_json", sa.JSON(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["receipt_batches.id"]),
        sa.ForeignKeyConstraint(["duplicate_of_receipt_id"], ["receipts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "image_sha256", name="uq_receipts_user_image_sha256"),
    )
    op.create_index(op.f("ix_receipts_batch_id"), "receipts", ["batch_id"], unique=False)
    op.create_index(op.f("ix_receipts_duplicate_status"), "receipts", ["duplicate_status"], unique=False)
    op.create_index(op.f("ix_receipts_id"), "receipts", ["id"], unique=False)
    op.create_index(op.f("ix_receipts_image_sha256"), "receipts", ["image_sha256"], unique=False)
    op.create_index(op.f("ix_receipts_status"), "receipts", ["status"], unique=False)
    op.create_index(op.f("ix_receipts_user_id"), "receipts", ["user_id"], unique=False)

    op.create_table(
        "receipt_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("style_no", sa.String(length=100), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("color", sa.String(length=100), nullable=True),
        sa.Column("size", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipt_items_id"), "receipt_items", ["id"], unique=False)
    op.create_index(op.f("ix_receipt_items_receipt_id"), "receipt_items", ["receipt_id"], unique=False)
    op.create_index(op.f("ix_receipt_items_style_no"), "receipt_items", ["style_no"], unique=False)

    op.create_table(
        "receipt_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("run_type", sa.String(length=50), nullable=False),
        sa.Column("first_round_model", sa.String(length=100), nullable=True),
        sa.Column("second_round_model", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.Column("corrected_json", sa.JSON(), nullable=True),
        sa.Column("final_json", sa.JSON(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipt_runs_id"), "receipt_runs", ["id"], unique=False)
    op.create_index(op.f("ix_receipt_runs_receipt_id"), "receipt_runs", ["receipt_id"], unique=False)
    op.create_index(op.f("ix_receipt_runs_run_type"), "receipt_runs", ["run_type"], unique=False)

    op.execute("INSERT INTO users (id, display_name, phone, openid) VALUES (1, '默认老板', NULL, NULL)")


def downgrade() -> None:
    op.drop_index(op.f("ix_receipt_runs_run_type"), table_name="receipt_runs")
    op.drop_index(op.f("ix_receipt_runs_receipt_id"), table_name="receipt_runs")
    op.drop_index(op.f("ix_receipt_runs_id"), table_name="receipt_runs")
    op.drop_table("receipt_runs")
    op.drop_index(op.f("ix_receipt_items_style_no"), table_name="receipt_items")
    op.drop_index(op.f("ix_receipt_items_receipt_id"), table_name="receipt_items")
    op.drop_index(op.f("ix_receipt_items_id"), table_name="receipt_items")
    op.drop_table("receipt_items")
    op.drop_index(op.f("ix_receipts_user_id"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_status"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_image_sha256"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_id"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_duplicate_status"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_batch_id"), table_name="receipts")
    op.drop_table("receipts")
    op.drop_index(op.f("ix_receipt_batches_user_id"), table_name="receipt_batches")
    op.drop_index(op.f("ix_receipt_batches_status"), table_name="receipt_batches")
    op.drop_index(op.f("ix_receipt_batches_id"), table_name="receipt_batches")
    op.drop_table("receipt_batches")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
