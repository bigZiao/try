import asyncio
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.receipt import Receipt
from app.models.receipt_task import ReceiptTask


class ReceiptTaskQueueService:
    COMPLETED_STATUSES = {"ready_for_review", "need_review", "confirmed"}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def enqueue_receipt(self, receipt: Receipt, task_type: str = "process_receipt") -> ReceiptTask:
        if self._has_processed_result(receipt):
            existing_task = (
                self.db.query(ReceiptTask)
                .filter(
                    ReceiptTask.receipt_id == receipt.id,
                    ReceiptTask.task_type == task_type,
                    ReceiptTask.status.in_(["queued", "running", "succeeded"]),
                )
                .order_by(ReceiptTask.id.desc())
                .first()
            )
            if existing_task is not None:
                return existing_task

            task = ReceiptTask(
                receipt_id=receipt.id,
                user_id=receipt.user_id,
                batch_id=receipt.batch_id,
                task_type=task_type,
                status="succeeded",
                attempts=0,
                max_attempts=max(self.settings.receipt_task_max_attempts, 1),
                finished_at=datetime.utcnow(),
                last_error="Skipped enqueue because receipt already has processed result",
            )
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
            return task

        task = ReceiptTask(
            receipt_id=receipt.id,
            user_id=receipt.user_id,
            batch_id=receipt.batch_id,
            task_type=task_type,
            status="queued",
            max_attempts=max(self.settings.receipt_task_max_attempts, 1),
        )
        receipt.status = "queued"
        receipt.note = None
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def recover_stale_tasks(self) -> list[int]:
        cutoff = datetime.utcnow() - timedelta(minutes=max(self.settings.receipt_task_stale_minutes, 1))
        tasks = (
            self.db.query(ReceiptTask)
            .filter(ReceiptTask.status == "running", ReceiptTask.locked_at < cutoff)
            .all()
        )
        task_ids: list[int] = []
        for task in tasks:
            receipt = self.db.get(Receipt, task.receipt_id)
            if receipt is not None and self._has_processed_result(receipt):
                task.status = "succeeded"
                task.locked_at = None
                task.finished_at = datetime.utcnow()
                task.last_error = "Skipped stale recovery because receipt already has processed result"
                continue
            if task.attempts >= task.max_attempts:
                task.status = "failed"
                task.last_error = "Task exceeded max attempts after stale recovery"
                task.finished_at = datetime.utcnow()
                if receipt is not None:
                    receipt.status = "failed"
                    receipt.note = task.last_error
            else:
                task.status = "queued"
                task.locked_at = None
                task.started_at = None
                task.last_error = "Recovered stale running task"
                task_ids.append(task.id)
                if receipt is not None and receipt.status != "confirmed":
                    receipt.status = "queued"
        self.db.commit()
        return task_ids

    @staticmethod
    async def process_task(task_id: int) -> None:
        from app.services.pipeline import ReceiptPipelineService

        settings = get_settings()
        max_attempts = max(settings.receipt_task_max_attempts, 1)
        for attempt_index in range(max_attempts):
            db = SessionLocal()
            task: ReceiptTask | None = None
            try:
                task = db.get(ReceiptTask, task_id)
                if task is None or task.status in {"succeeded", "dead"}:
                    return
                task.status = "running"
                task.attempts += 1
                task.locked_at = datetime.utcnow()
                task.started_at = task.started_at or datetime.utcnow()
                task.last_error = None
                db.commit()

                await ReceiptPipelineService(db, task_id=task.id).process_receipt(task.receipt_id)

                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                task.locked_at = None
                db.commit()
                return
            except Exception as exc:
                if task is not None:
                    task.last_error = str(exc)
                    task.locked_at = None
                    if task.attempts >= task.max_attempts:
                        task.status = "failed"
                        task.finished_at = datetime.utcnow()
                    else:
                        task.status = "queued"
                    db.commit()
                if attempt_index < max_attempts - 1:
                    await asyncio.sleep(2 * (attempt_index + 1))
                    continue
                return
            finally:
                db.close()

    @staticmethod
    async def process_tasks(task_ids: list[int]) -> None:
        settings = get_settings()
        semaphore = asyncio.Semaphore(max(settings.batch_processing_concurrency, 1))

        async def worker(task_id: int) -> None:
            async with semaphore:
                await ReceiptTaskQueueService.process_task(task_id)

        await asyncio.gather(*(worker(task_id) for task_id in task_ids))

    def _has_processed_result(self, receipt: Receipt) -> bool:
        has_result = bool(receipt.final_json or receipt.corrected_json or receipt.structured_json)
        return receipt.status in self.COMPLETED_STATUSES and has_result
