from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.receipt import Receipt
from app.schemas.receipt import (
    ConfirmReceiptRequest,
    ManualReceiptRequest,
    ReceiptListItemResponse,
    ReceiptListResponse,
    ReceiptResponse,
    ReceiptRunResponse,
    ReviewReceiptFieldsRequest,
    ReviewReceiptItemRequest,
    VisionRerunRequest,
)
from app.services.excel_exporter import ExcelExportService
from app.services.pipeline import ReceiptPipelineService
from app.services.task_queue import ReceiptTaskQueueService

router = APIRouter(prefix="/receipts", tags=["receipts"])


def current_user_id(x_user_id: int = Header(1, alias="X-User-Id")) -> int:
    return x_user_id


@router.post("", response_model=ReceiptResponse)
async def upload_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    service = ReceiptPipelineService(db)
    receipt, duplicate = await service.create_pending_receipt(file, user_id=user_id)
    if not duplicate:
        task = ReceiptTaskQueueService(db).enqueue_receipt(receipt)
        background_tasks.add_task(ReceiptTaskQueueService.process_task, task.id)
    return receipt


@router.get("", response_model=ReceiptListResponse)
def list_receipts(
    status: str | None = None,
    batch_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> ReceiptListResponse:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    query = db.query(Receipt).filter(Receipt.user_id == user_id)
    if status:
        query = query.filter(Receipt.status == status)
    if batch_id is not None:
        query = query.filter(Receipt.batch_id == batch_id)

    total = query.count()
    receipts = query.order_by(Receipt.id.desc()).offset(offset).limit(limit).all()
    return ReceiptListResponse(
        items=[_receipt_list_item(receipt) for receipt in receipts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/manual", response_model=ReceiptResponse)
def create_manual_receipt(
    payload: ManualReceiptRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    service = ReceiptPipelineService(db)
    return service.create_manual_receipt(payload.model_dump(exclude_none=True), user_id=user_id)


@router.get("/export.xlsx")
def export_receipts(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    receipts = (
        db.query(Receipt)
        .filter(Receipt.user_id == user_id, Receipt.status.in_(["ready_for_review", "confirmed"]))
        .order_by(Receipt.id.asc())
        .all()
    )
    content = ExcelExportService().export_receipts(receipts)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="receipts.xlsx"'},
    )


@router.get("/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(
    receipt_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.post("/{receipt_id}/confirm", response_model=ReceiptResponse)
def confirm_receipt(
    receipt_id: int,
    payload: ConfirmReceiptRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return service.confirm(receipt_id, payload.final_json)


@router.patch("/{receipt_id}/review-fields", response_model=ReceiptResponse)
def update_review_fields(
    receipt_id: int,
    payload: ReviewReceiptFieldsRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return service.update_review_fields(receipt_id, payload.fields, payload.summary)


@router.post("/{receipt_id}/review-items", response_model=ReceiptResponse)
def add_review_item(
    receipt_id: int,
    payload: ReviewReceiptItemRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return service.add_review_item(receipt_id, payload.model_dump(exclude_unset=True, exclude_none=True))


@router.patch("/{receipt_id}/review-items/{item_index}", response_model=ReceiptResponse)
def update_review_item(
    receipt_id: int,
    item_index: int,
    payload: ReviewReceiptItemRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return service.update_review_item(receipt_id, item_index, payload.model_dump(exclude_unset=True, exclude_none=True))


@router.delete("/{receipt_id}/review-items/{item_index}", response_model=ReceiptResponse)
def delete_review_item(
    receipt_id: int,
    item_index: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return service.delete_review_item(receipt_id, item_index)


@router.post("/{receipt_id}/retry", response_model=ReceiptResponse)
def retry_receipt(
    receipt_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.duplicate_status != "unique":
        raise HTTPException(status_code=400, detail="Duplicate receipt cannot be retried")

    service = ReceiptPipelineService(db)
    receipt = service.retry(receipt_id)
    task = ReceiptTaskQueueService(db).enqueue_receipt(receipt)
    background_tasks.add_task(ReceiptTaskQueueService.process_task, task.id)
    return receipt


@router.get("/{receipt_id}/image")
def get_receipt_image(
    receipt_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if receipt.source_type == "manual" or not receipt.image_path:
        raise HTTPException(status_code=404, detail="Manual receipt has no image")

    image_path = Path(receipt.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Receipt image not found")
    return FileResponse(image_path)


@router.post("/{receipt_id}/vision-rerun", response_model=ReceiptRunResponse)
async def vision_rerun_receipt(
    receipt_id: int,
    payload: VisionRerunRequest,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    service = ReceiptPipelineService(db)
    return await service.vision_rerun(
        receipt_id=receipt_id,
        apply_result=payload.apply_result,
        reason=payload.reason,
    )


@router.get("/{receipt_id}/export.xlsx")
def export_receipt(
    receipt_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receipt not found")

    content = ExcelExportService().export_receipts([receipt])
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="receipt-{receipt_id}.xlsx"'},
    )


def _receipt_list_item(receipt: Receipt) -> ReceiptListItemResponse:
    data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return ReceiptListItemResponse(
        id=receipt.id,
        user_id=receipt.user_id,
        batch_id=receipt.batch_id,
        source_type=receipt.source_type,
        original_filename=receipt.original_filename,
        duplicate_status=receipt.duplicate_status,
        status=receipt.status,
        merchant_name=_str_or_none(data.get("merchant_name")),
        order_date=_str_or_none(data.get("order_date")),
        customer_name=_str_or_none(data.get("customer_name")),
        total_quantity=_int_or_none(summary.get("total_quantity")),
        total_amount=_str_or_none(summary.get("total_amount")),
        need_review=data.get("need_review") if isinstance(data.get("need_review"), bool) else None,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
    )


def _str_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
