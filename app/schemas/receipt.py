from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReceiptItem(BaseModel):
    style_no: str | None = None
    product_name: str | None = None
    color: str | None = None
    size: str | None = None
    quantity: int = 0
    unit_price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")


class StructuredReceipt(BaseModel):
    ticket_no: str | None = None
    receipt_date: str | None = None
    supplier: str | None = None
    customer: str | None = None
    items: list[ReceiptItem] = Field(default_factory=list)
    total_quantity: int | None = None
    total_amount: Decimal | None = None
    notes: str | None = None


class ConfirmReceiptRequest(BaseModel):
    final_json: dict[str, Any]


class VisionRerunRequest(BaseModel):
    apply_result: bool = False
    reason: str | None = None


class ReceiptRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    run_type: str
    first_round_model: str | None = None
    second_round_model: str | None = None
    reason: str | None = None
    status: str
    applied: bool
    structured_json: dict[str, Any] | None = None
    corrected_json: dict[str, Any] | None = None
    final_json: dict[str, Any] | None = None
    validation_errors: list[Any] | None = None
    created_at: datetime


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    image_path: str
    status: str
    ocr_json: dict[str, Any] | None = None
    structured_json: dict[str, Any] | None = None
    corrected_json: dict[str, Any] | None = None
    final_json: dict[str, Any] | None = None
    validation_errors: list[Any] | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime
