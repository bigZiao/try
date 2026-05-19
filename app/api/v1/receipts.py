from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.receipt import Receipt
from app.schemas.receipt import ConfirmReceiptRequest, ReceiptResponse, ReceiptRunResponse, VisionRerunRequest
from app.services.excel_exporter import ExcelExportService
from app.services.pipeline import ReceiptPipelineService

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Receipt:
    service = ReceiptPipelineService(db)
    return await service.create_and_process(file)


@router.get("/export.xlsx")
def export_receipts(db: Session = Depends(get_db)) -> StreamingResponse:
    receipts = (
        db.query(Receipt)
        .filter(Receipt.status.in_(["ready_for_review", "confirmed"]))
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
def get_receipt(receipt_id: int, db: Session = Depends(get_db)) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.post("/{receipt_id}/confirm", response_model=ReceiptResponse)
def confirm_receipt(
    receipt_id: int,
    payload: ConfirmReceiptRequest,
    db: Session = Depends(get_db),
) -> Receipt:
    service = ReceiptPipelineService(db)
    return service.confirm(receipt_id, payload.final_json)


@router.post("/{receipt_id}/vision-rerun", response_model=ReceiptRunResponse)
async def vision_rerun_receipt(
    receipt_id: int,
    payload: VisionRerunRequest,
    db: Session = Depends(get_db),
):
    service = ReceiptPipelineService(db)
    return await service.vision_rerun(
        receipt_id=receipt_id,
        apply_result=payload.apply_result,
        reason=payload.reason,
    )


@router.get("/{receipt_id}/export.xlsx")
def export_receipt(receipt_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    content = ExcelExportService().export_receipts([receipt])
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="receipt-{receipt_id}.xlsx"'},
    )
