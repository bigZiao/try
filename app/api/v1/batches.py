from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.receipt import Receipt
from app.models.receipt_batch import ReceiptBatch
from app.schemas.receipt import BatchReceiptUploadResult, ReceiptBatchResponse
from app.services.excel_exporter import ExcelExportService
from app.services.pipeline import ReceiptPipelineService
from app.services.task_queue import ReceiptTaskQueueService

router = APIRouter(prefix="/batches", tags=["batches"])


def current_user_id(x_user_id: int = Header(1, alias="X-User-Id")) -> int:
    return x_user_id


@router.post("", response_model=ReceiptBatchResponse)
async def create_batch(
    background_tasks: BackgroundTasks,
    title: str | None = Form(None),
    files: list[UploadFile] = File(...),
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> ReceiptBatchResponse:
    service = ReceiptPipelineService(db)
    service.ensure_user(user_id)
    batch = ReceiptBatch(user_id=user_id, title=title, status="uploaded")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    upload_results: list[BatchReceiptUploadResult] = []
    task_ids_to_process: list[int] = []
    for file in files:
        receipt, duplicate = await service.create_pending_receipt(file, user_id=user_id, batch_id=batch.id)
        if duplicate:
            upload_results.append(
                BatchReceiptUploadResult(
                    receipt_id=receipt.id,
                    filename=file.filename or receipt.original_filename,
                    status=receipt.status,
                    duplicate=True,
                    duplicate_of_receipt_id=receipt.id,
                )
            )
            continue

        upload_results.append(
            BatchReceiptUploadResult(
                receipt_id=receipt.id,
                filename=receipt.original_filename,
                status=receipt.status,
                duplicate=False,
            )
        )
        task = ReceiptTaskQueueService(db).enqueue_receipt(receipt)
        task_ids_to_process.append(task.id)

    batch.status = "queued" if any(not result.duplicate for result in upload_results) else "empty"
    db.commit()
    db.refresh(batch)
    if task_ids_to_process:
        background_tasks.add_task(ReceiptTaskQueueService.process_tasks, task_ids_to_process)
    return _batch_response(batch, upload_results, db)


@router.get("/{batch_id}", response_model=ReceiptBatchResponse)
def get_batch(
    batch_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> ReceiptBatchResponse:
    batch = db.get(ReceiptBatch, batch_id)
    if batch is None or batch.user_id != user_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    receipts = (
        db.query(Receipt)
        .filter(Receipt.batch_id == batch.id, Receipt.user_id == user_id)
        .order_by(Receipt.id.asc())
        .all()
    )
    upload_results = [
        BatchReceiptUploadResult(
            receipt_id=receipt.id,
            filename=receipt.original_filename,
            status=receipt.status,
            duplicate=receipt.duplicate_status != "unique",
            duplicate_of_receipt_id=receipt.duplicate_of_receipt_id,
        )
        for receipt in receipts
    ]
    return _batch_response(batch, upload_results, db)


@router.get("/{batch_id}/export.xlsx")
def export_batch(
    batch_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    batch = db.get(ReceiptBatch, batch_id)
    if batch is None or batch.user_id != user_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    receipts = (
        db.query(Receipt)
        .filter(
            Receipt.batch_id == batch.id,
            Receipt.user_id == user_id,
            Receipt.status.in_(["ready_for_review", "confirmed"]),
        )
        .order_by(Receipt.id.asc())
        .all()
    )
    content = ExcelExportService().export_receipts(receipts)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}.xlsx"'},
    )


def _batch_response(
    batch: ReceiptBatch,
    receipts: list[BatchReceiptUploadResult],
    db: Session,
) -> ReceiptBatchResponse:
    rows = db.query(Receipt.status, Receipt.duplicate_status).filter(Receipt.batch_id == batch.id).all()
    counts: dict[str, int] = {}
    duplicate_count = 0
    processing_count = 0
    ready_for_review_count = 0
    need_review_count = 0
    confirmed_count = 0
    failed_count = 0

    for status, duplicate_status in rows:
        counts[status] = counts.get(status, 0) + 1
        if duplicate_status != "unique":
            duplicate_count += 1
            continue
        if status in {"uploaded", "queued", "ocr_processing", "llm_structuring", "rule_checking", "vision_processing"}:
            processing_count += 1
        elif status == "ready_for_review":
            ready_for_review_count += 1
        elif status == "need_review":
            need_review_count += 1
        elif status == "confirmed":
            confirmed_count += 1
        elif status == "failed":
            failed_count += 1

    total_count = len(rows)
    completed_count = duplicate_count + ready_for_review_count + need_review_count + confirmed_count + failed_count
    progress_percent = int(completed_count * 100 / total_count) if total_count else 0
    return ReceiptBatchResponse(
        id=batch.id,
        user_id=batch.user_id,
        title=batch.title,
        status=batch.status,
        note=batch.note,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        receipts=receipts,
        counts=counts,
        total_count=total_count,
        duplicate_count=duplicate_count,
        processing_count=processing_count,
        ready_for_review_count=ready_for_review_count,
        need_review_count=need_review_count,
        confirmed_count=confirmed_count,
        failed_count=failed_count,
        completed_count=completed_count,
        progress_percent=progress_percent,
    )
