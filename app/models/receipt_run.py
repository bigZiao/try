from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReceiptRun(Base):
    __tablename__ = "receipt_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    first_round_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    second_round_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    corrected_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
