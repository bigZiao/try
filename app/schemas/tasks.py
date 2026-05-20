from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReceiptTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    user_id: int
    batch_id: int | None = None
    task_type: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProviderCallLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int | None = None
    task_id: int | None = None
    provider: str
    stage: str
    model: str | None = None
    status: str
    duration_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class RecoverTasksResponse(BaseModel):
    recovered_task_ids: list[int]
