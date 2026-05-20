"""tasks auth logs

Revision ID: 20260520_0002
Revises: 20260520_0001
Create Date: 2026-05-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260520_0002"
down_revision: str | None = "20260520_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_key", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=30), nullable=False, server_default="owner"))
    op.add_column("users", sa.Column("status", sa.String(length=30), nullable=False, server_default="active"))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)

    op.create_table(
        "receipt_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["receipt_batches.id"]),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipt_tasks_batch_id"), "receipt_tasks", ["batch_id"], unique=False)
    op.create_index(op.f("ix_receipt_tasks_id"), "receipt_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_receipt_tasks_receipt_id"), "receipt_tasks", ["receipt_id"], unique=False)
    op.create_index(op.f("ix_receipt_tasks_status"), "receipt_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_receipt_tasks_task_type"), "receipt_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_receipt_tasks_user_id"), "receipt_tasks", ["user_id"], unique=False)

    op.create_table(
        "provider_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["receipt_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_provider_call_logs_id"), "provider_call_logs", ["id"], unique=False)
    op.create_index(op.f("ix_provider_call_logs_provider"), "provider_call_logs", ["provider"], unique=False)
    op.create_index(op.f("ix_provider_call_logs_receipt_id"), "provider_call_logs", ["receipt_id"], unique=False)
    op.create_index(op.f("ix_provider_call_logs_stage"), "provider_call_logs", ["stage"], unique=False)
    op.create_index(op.f("ix_provider_call_logs_status"), "provider_call_logs", ["status"], unique=False)
    op.create_index(op.f("ix_provider_call_logs_task_id"), "provider_call_logs", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_call_logs_task_id"), table_name="provider_call_logs")
    op.drop_index(op.f("ix_provider_call_logs_status"), table_name="provider_call_logs")
    op.drop_index(op.f("ix_provider_call_logs_stage"), table_name="provider_call_logs")
    op.drop_index(op.f("ix_provider_call_logs_receipt_id"), table_name="provider_call_logs")
    op.drop_index(op.f("ix_provider_call_logs_provider"), table_name="provider_call_logs")
    op.drop_index(op.f("ix_provider_call_logs_id"), table_name="provider_call_logs")
    op.drop_table("provider_call_logs")

    op.drop_index(op.f("ix_receipt_tasks_user_id"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_task_type"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_status"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_receipt_id"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_id"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_batch_id"), table_name="receipt_tasks")
    op.drop_table("receipt_tasks")

    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "status")
    op.drop_column("users", "role")
    op.drop_column("users", "session_key")
