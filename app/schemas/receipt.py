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


class ReviewReceiptItemRequest(BaseModel):
    style_no: str | None = None
    product_name: str | None = None
    color: str | None = None
    size: str | None = None
    sizes: list[dict[str, Any]] | dict[str, Any] | None = None
    quantity: int | None = None
    unit_price: Decimal | int | float | str | None = None
    subtotal: Decimal | int | float | str | None = None
    block_indexes: list[int] = Field(default_factory=list)


class ReviewReceiptFieldsRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] | None = None


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
    user_id: int
    batch_id: int | None = None
    original_filename: str
    image_path: str
    image_sha256: str
    duplicate_of_receipt_id: int | None = None
    duplicate_status: str
    status: str
    ocr_json: dict[str, Any] | None = None
    structured_json: dict[str, Any] | None = None
    corrected_json: dict[str, Any] | None = None
    final_json: dict[str, Any] | None = None
    validation_errors: list[Any] | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class BatchReceiptUploadResult(BaseModel):
    receipt_id: int
    filename: str
    status: str
    duplicate: bool = False
    duplicate_of_receipt_id: int | None = None


class ReceiptBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None = None
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    receipts: list[BatchReceiptUploadResult] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    total_count: int = 0
    duplicate_count: int = 0
    processing_count: int = 0
    ready_for_review_count: int = 0
    need_review_count: int = 0
    confirmed_count: int = 0
    failed_count: int = 0
    completed_count: int = 0
    progress_percent: int = 0
