from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)

    ocr_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    corrected_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
