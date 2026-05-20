from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.receipt import Receipt
from app.schemas.receipt import (
    ConfirmReceiptRequest,
    ReceiptResponse,
    ReceiptRunResponse,
    ReviewReceiptFieldsRequest,
    ReviewReceiptItemRequest,
    VisionRerunRequest,
)
from app.services.excel_exporter import ExcelExportService
from app.services.pipeline import ReceiptPipelineService

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
        background_tasks.add_task(ReceiptPipelineService.process_receipt_task, receipt.id)
    return receipt


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
    background_tasks.add_task(ReceiptPipelineService.process_receipt_task, receipt.id)
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
