from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.provider_call_log import ProviderCallLog
from app.models.receipt_task import ReceiptTask
from app.schemas.tasks import ProviderCallLogResponse, ReceiptTaskResponse, RecoverTasksResponse
from app.services.task_queue import ReceiptTaskQueueService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def require_admin(x_admin_token: str | None = Header(None, alias="X-Admin-Token")) -> None:
    expected = get_settings().admin_token
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin token is invalid")


@router.get("", response_model=list[ReceiptTaskResponse])
def list_tasks(
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[ReceiptTask]:
    return db.query(ReceiptTask).order_by(ReceiptTask.id.desc()).limit(min(limit, 500)).all()


@router.post("/recover-stale", response_model=RecoverTasksResponse)
def recover_stale_tasks(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RecoverTasksResponse:
    task_ids = ReceiptTaskQueueService(db).recover_stale_tasks()
    if task_ids:
        background_tasks.add_task(ReceiptTaskQueueService.process_tasks, task_ids)
    return RecoverTasksResponse(recovered_task_ids=task_ids)


@router.get("/calls", response_model=list[ProviderCallLogResponse])
def list_provider_call_logs(
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
    receipt_id: int | None = None,
    limit: int = 100,
) -> list[ProviderCallLog]:
    query = db.query(ProviderCallLog)
    if receipt_id is not None:
        query = query.filter(ProviderCallLog.receipt_id == receipt_id)
    return query.order_by(ProviderCallLog.id.desc()).limit(min(limit, 500)).all()
