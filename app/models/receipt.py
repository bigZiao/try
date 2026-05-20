from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("user_id", "image_sha256", name="uq_receipts_user_image_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True, default=1)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("receipt_batches.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="image", index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duplicate_of_receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id"), nullable=True)
    duplicate_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unique", index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)

    ocr_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    corrected_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
