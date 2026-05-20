import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.adapters.llm import get_llm_adapter
from app.adapters.ocr import get_ocr_adapter
from app.adapters.vision_llm import get_vision_llm_adapter
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.receipt_batch import ReceiptBatch
from app.models.receipt_item import ReceiptItem
from app.models.receipt import Receipt
from app.models.receipt_run import ReceiptRun
from app.models.user import User
from app.services.normalizer import ReceiptNormalizer
from app.services.image_preprocessor import ImagePreprocessService
from app.services.call_logger import ProviderCallLogger
from app.services.rule_engine import RuleEngine
from app.services.storage import ImageStorageService


_limiters: dict[tuple[int, str], tuple[int, asyncio.Semaphore]] = {}


def _get_limiter(name: str, limit: int) -> asyncio.Semaphore:
    normalized_limit = max(limit, 1)
    key = (id(asyncio.get_running_loop()), name)
    current = _limiters.get(key)
    if current is None or current[0] != normalized_limit:
        current = (normalized_limit, asyncio.Semaphore(normalized_limit))
        _limiters[key] = current
    return current[1]


class ReceiptPipelineService:
    def __init__(self, db: Session, task_id: int | None = None) -> None:
        self.db = db
        self.task_id = task_id
        self.storage = ImageStorageService()
        self.ocr = get_ocr_adapter()
        self.llm = get_llm_adapter()
        self.vision_llm = get_vision_llm_adapter()
        self.rules = RuleEngine()
        self.normalizer = ReceiptNormalizer()
        self.image_preprocessor = ImagePreprocessService()
        self.settings = get_settings()

    def ensure_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is not None:
            return user

        if user_id != 1:
            raise HTTPException(status_code=404, detail="User not found")

        user = User(id=1, display_name="默认老板", role="owner", status="active", is_admin=True)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    async def create_pending_receipt(
        self,
        file: UploadFile,
        user_id: int = 1,
        batch_id: int | None = None,
    ) -> tuple[Receipt, bool]:
        self.ensure_user(user_id)
        image_path, image_sha256 = await self.storage.save_upload(file)
        duplicate = (
            self.db.query(Receipt)
            .filter(Receipt.user_id == user_id, Receipt.image_sha256 == image_sha256)
            .order_by(Receipt.id.asc())
            .first()
        )
        if duplicate is not None:
            try:
                Path(image_path).unlink(missing_ok=True)
            except OSError:
                pass
            return duplicate, True

        receipt = Receipt(
            user_id=user_id,
            batch_id=batch_id,
            original_filename=file.filename or "upload",
            image_path=str(image_path),
            image_sha256=image_sha256,
            duplicate_status="unique",
            status="uploaded",
        )
        self.db.add(receipt)
        self.db.commit()
        self.db.refresh(receipt)
        return receipt, False

    async def create_and_process(self, file: UploadFile, user_id: int = 1) -> Receipt:
        receipt, is_duplicate = await self.create_pending_receipt(file, user_id=user_id)
        if is_duplicate:
            return receipt

        return await self.process_receipt(receipt.id)

    def create_manual_receipt(self, payload: dict[str, Any], user_id: int = 1) -> Receipt:
        user = self.ensure_user(user_id)
        data = dict(payload)
        data.setdefault("parse_status", "manual")
        data.setdefault("bill_type", "manual_receipt")
        data.setdefault("customer_name", user.display_name)
        data.setdefault("payments", [])
        data.setdefault("warnings", [])
        data.setdefault("need_review", False)
        data.setdefault("confidence", 1)
        data.setdefault("confidence_reason", "Manual entry by owner.")

        normalized_json = self.normalizer.normalize(data)
        errors = self.rules.validate(normalized_json)
        digest = sha256(f"manual:{user_id}:{uuid4().hex}".encode("utf-8")).hexdigest()
        receipt = Receipt(
            user_id=user_id,
            source_type="manual",
            original_filename="manual",
            image_path="",
            image_sha256=digest,
            duplicate_status="unique",
            status=self._status_for_validated_json(normalized_json, errors),
            final_json=normalized_json,
            validation_errors=errors,
            note=payload.get("note"),
        )
        self.db.add(receipt)
        self.db.commit()
        if receipt.status == "confirmed":
            self._sync_receipt_items(receipt)
            self.db.commit()
        self.db.refresh(receipt)
        return receipt

    async def process_receipt(self, receipt_id: int) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        if self._has_processed_result(receipt):
            return receipt
        image_path = Path(receipt.image_path)
        try:
            ocr_image_path = self.image_preprocessor.prepare_for_ocr(image_path)
            logger = ProviderCallLogger(self.db, receipt_id=receipt.id, task_id=self.task_id)
            receipt.status = "ocr_processing"
            self.db.commit()

            receipt.ocr_json = await logger.record(
                provider=self.settings.ocr_provider,
                stage="ocr",
                model=self.settings.baidu_endpoint if self.settings.ocr_provider.lower() == "baidu" else "mock",
                factory=lambda: self._limited(
                    "ocr",
                    self.settings.ocr_concurrency,
                    lambda: self.ocr.recognize(ocr_image_path),
                ),
                metadata={"image_path": str(ocr_image_path)},
            )
            receipt.status = "llm_structuring"
            self.db.commit()

            structured_json = self.normalizer.normalize(
                await logger.record(
                    provider=self.settings.llm_provider,
                    stage="llm_first_round",
                    model=self.settings.llm_model,
                    factory=lambda: self._limited(
                        "llm",
                        self.settings.llm_concurrency,
                        lambda: self.llm.structure_receipt(receipt.ocr_json),
                    ),
                )
            )
            result = await self._run_rule_and_correction(structured_json, receipt.ocr_json, receipt.id)
            receipt.structured_json = result["structured_json"]
            receipt.corrected_json = result["corrected_json"]
            receipt.final_json = result["final_json"]
            receipt.validation_errors = result["validation_errors"]
            receipt.status = result["status"]
            if receipt.final_json and receipt.status == "confirmed":
                self._sync_receipt_items(receipt)
            self.db.commit()
            self.db.refresh(receipt)
            self._refresh_batch_status(receipt.batch_id)
            return receipt
        except Exception as exc:
            receipt.status = "failed"
            receipt.note = str(exc)
            self.db.commit()
            self._refresh_batch_status(receipt.batch_id)
            self.db.refresh(receipt)
            raise

    @staticmethod
    async def process_receipt_task(receipt_id: int) -> None:
        db = SessionLocal()
        try:
            await ReceiptPipelineService(db).process_receipt(receipt_id)
        finally:
            db.close()

    @staticmethod
    async def process_receipts_task(receipt_ids: list[int]) -> None:
        settings = get_settings()
        semaphore = asyncio.Semaphore(max(settings.batch_processing_concurrency, 1))

        async def worker(receipt_id: int) -> None:
            async with semaphore:
                db = SessionLocal()
                try:
                    await ReceiptPipelineService(db).process_receipt(receipt_id)
                except Exception:
                    # process_receipt already persists failed status and note.
                    return
                finally:
                    db.close()

        await asyncio.gather(*(worker(receipt_id) for receipt_id in receipt_ids))

    def retry(self, receipt_id: int) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")

        receipt.status = "queued"
        receipt.note = None
        receipt.ocr_json = None
        receipt.structured_json = None
        receipt.corrected_json = None
        receipt.final_json = None
        receipt.validation_errors = None
        self.db.query(ReceiptItem).filter(ReceiptItem.receipt_id == receipt.id).delete()
        self.db.commit()
        self._refresh_batch_status(receipt.batch_id)
        self.db.refresh(receipt)
        return receipt

    async def vision_rerun(
        self,
        receipt_id: int,
        apply_result: bool = False,
        reason: str | None = None,
    ) -> ReceiptRun:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        if not receipt.ocr_json:
            raise HTTPException(status_code=400, detail="Receipt has no OCR JSON")

        vision_image_path = self.image_preprocessor.prepare_for_ocr(Path(receipt.image_path))
        logger = ProviderCallLogger(self.db, receipt_id=receipt.id, task_id=self.task_id)
        structured_json = self.normalizer.normalize(
            await logger.record(
                provider=self.settings.vision_llm_provider,
                stage="vision_first_round",
                model=self.settings.vision_llm_model,
                factory=lambda: self._limited(
                    "vision_llm",
                    self.settings.vision_llm_concurrency,
                    lambda: self.vision_llm.structure_receipt(
                        image_path=vision_image_path,
                        ocr_json=receipt.ocr_json,
                        reason=reason,
                    ),
                ),
                metadata={"image_path": str(vision_image_path), "reason": reason},
            )
        )
        result = await self._run_rule_and_correction(structured_json, receipt.ocr_json, receipt.id)

        run = ReceiptRun(
            receipt_id=receipt.id,
            run_type="vision_rerun",
            first_round_model="vision",
            second_round_model=getattr(self.llm, "settings", None).llm_model if hasattr(self.llm, "settings") else None,
            reason=reason,
            status=result["status"],
            applied=apply_result,
            structured_json=result["structured_json"],
            corrected_json=result["corrected_json"],
            final_json=result["final_json"],
            validation_errors=result["validation_errors"],
        )
        self.db.add(run)

        if apply_result:
            receipt.structured_json = result["structured_json"]
            receipt.corrected_json = result["corrected_json"]
            receipt.final_json = result["final_json"]
            receipt.validation_errors = result["validation_errors"]
            receipt.status = result["status"]
            if receipt.final_json and receipt.status == "confirmed":
                self._sync_receipt_items(receipt)

        self.db.commit()
        self.db.refresh(run)
        return run

    async def _run_rule_and_correction(
        self,
        structured_json: dict[str, Any],
        ocr_json: dict[str, Any],
        receipt_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_structured = self.normalizer.normalize(structured_json)
        first_errors = self.rules.validate(normalized_structured)

        if not first_errors:
            return {
                "structured_json": normalized_structured,
                "corrected_json": None,
                "final_json": normalized_structured,
                "validation_errors": [],
                "status": self._status_for_validated_json(normalized_structured, []),
            }

        corrected_json = self.normalizer.normalize(
            await ProviderCallLogger(self.db, receipt_id=receipt_id, task_id=self.task_id).record(
                provider=self.settings.llm_provider,
                stage="llm_second_round",
                model=self.settings.llm_model,
                factory=lambda: self._limited(
                    "llm",
                    self.settings.llm_concurrency,
                    lambda: self.llm.correct_receipt(
                        normalized_structured,
                        first_errors,
                        ocr_json,
                    ),
                ),
            )
        )
        second_errors = self.rules.validate(corrected_json)
        final_json = corrected_json if not second_errors else normalized_structured
        return {
            "structured_json": normalized_structured,
            "corrected_json": corrected_json,
            "final_json": final_json,
            "validation_errors": second_errors,
            "status": self._status_for_validated_json(final_json, second_errors),
        }

    def confirm(self, receipt_id: int, final_json: dict[str, Any]) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")

        return self._save_review_json(receipt, final_json, confirmed=True)

    def update_review_fields(
        self,
        receipt_id: int,
        fields: dict[str, Any],
        summary: dict[str, Any] | None = None,
    ) -> Receipt:
        receipt = self._get_receipt_or_404(receipt_id)
        self._ensure_editable(receipt)
        data = self._editable_json(receipt)
        for key, value in fields.items():
            data[key] = value
        if summary is not None:
            current_summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
            data["summary"] = {**current_summary, **summary}
        return self._save_review_json(receipt, data)

    def add_review_item(self, receipt_id: int, item: dict[str, Any]) -> Receipt:
        receipt = self._get_receipt_or_404(receipt_id)
        self._ensure_editable(receipt)
        data = self._editable_json(receipt)
        items = data.get("items") if isinstance(data.get("items"), list) else []
        items.append(item)
        data["items"] = items
        return self._save_review_json(receipt, data)

    def update_review_item(self, receipt_id: int, item_index: int, item: dict[str, Any]) -> Receipt:
        receipt = self._get_receipt_or_404(receipt_id)
        self._ensure_editable(receipt)
        data = self._editable_json(receipt)
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if item_index < 0 or item_index >= len(items):
            raise HTTPException(status_code=404, detail="Receipt item not found")

        current_item = items[item_index] if isinstance(items[item_index], dict) else {}
        items[item_index] = {**current_item, **item}
        data["items"] = items
        return self._save_review_json(receipt, data)

    def delete_review_item(self, receipt_id: int, item_index: int) -> Receipt:
        receipt = self._get_receipt_or_404(receipt_id)
        self._ensure_editable(receipt)
        data = self._editable_json(receipt)
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if item_index < 0 or item_index >= len(items):
            raise HTTPException(status_code=404, detail="Receipt item not found")

        del items[item_index]
        data["items"] = items
        return self._save_review_json(receipt, data)

    def _get_receipt_or_404(self, receipt_id: int) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        return receipt

    def _editable_json(self, receipt: Receipt) -> dict[str, Any]:
        source = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
        data = dict(source)
        items = data.get("items")
        data["items"] = [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        return data

    def _ensure_editable(self, receipt: Receipt) -> None:
        return None

    def _save_review_json(
        self,
        receipt: Receipt,
        final_json: dict[str, Any],
        confirmed: bool = False,
    ) -> Receipt:
        normalized_json = self.normalizer.normalize(final_json)
        errors = self.rules.validate(normalized_json)
        receipt.final_json = normalized_json
        receipt.validation_errors = errors
        receipt.status = self._status_for_validated_json(normalized_json, errors)
        if receipt.status in {"ready_for_review", "confirmed"}:
            self._sync_receipt_items(receipt)
        else:
            self.db.query(ReceiptItem).filter(ReceiptItem.receipt_id == receipt.id).delete()
        self.db.commit()
        self._refresh_batch_status(receipt.batch_id)
        self.db.refresh(receipt)
        return receipt

    def _status_for_validated_json(self, data: dict[str, Any], errors: list[dict[str, Any]]) -> str:
        if errors:
            return "need_review"
        if data.get("need_review") is True:
            return "need_review"
        return "confirmed"

    def _has_processed_result(self, receipt: Receipt) -> bool:
        has_result = bool(receipt.final_json or receipt.corrected_json or receipt.structured_json)
        return receipt.status in {"ready_for_review", "need_review", "confirmed"} and has_result

    def _sync_receipt_items(self, receipt: Receipt) -> None:
        data = receipt.final_json or {}
        items = data.get("items") if isinstance(data.get("items"), list) else []
        self.db.query(ReceiptItem).filter(ReceiptItem.receipt_id == receipt.id).delete()

        row_no = 1
        for item in items:
            if not isinstance(item, dict):
                continue
            for size, quantity in self._expand_size_rows(item):
                self.db.add(
                    ReceiptItem(
                        receipt_id=receipt.id,
                        row_no=row_no,
                        style_no=self._get(item, "style_no", "sku_id", "item_code", "product_code"),
                        product_name=self._get(item, "product_name", "sku_name", "name", "item_name"),
                        color=self._get(item, "color", "color_name"),
                        size=size,
                        quantity=self._int(quantity),
                        unit_price=self._decimal(self._get(item, "unit_price")),
                        subtotal=self._decimal(self._get(item, "unit_price")) * self._decimal(quantity),
                    )
                )
                row_no += 1

    def _refresh_batch_status(self, batch_id: int | None) -> None:
        if batch_id is None:
            return
        batch = self.db.get(ReceiptBatch, batch_id)
        if batch is None:
            return
        statuses = [
            row[0]
            for row in self.db.query(Receipt.status)
            .filter(Receipt.batch_id == batch_id, Receipt.duplicate_status == "unique", Receipt.deleted_at.is_(None))
            .all()
        ]
        if not statuses:
            batch.status = "empty"
        elif all(status in {"ready_for_review", "need_review", "confirmed", "failed"} for status in statuses):
            if any(status == "failed" for status in statuses):
                batch.status = "partial_failed"
            elif any(status == "need_review" for status in statuses):
                batch.status = "need_review"
            elif all(status == "confirmed" for status in statuses):
                batch.status = "confirmed"
            else:
                batch.status = "ready_for_review"
        else:
            batch.status = "processing"
        self.db.commit()

    def _expand_size_rows(self, item: dict[str, Any]) -> list[tuple[Any, Any]]:
        sizes = self._get(item, "sizes", "size_quantities")
        if isinstance(sizes, dict):
            rows = [(size, quantity) for size, quantity in sizes.items()]
            if rows:
                return rows
        if isinstance(sizes, list):
            rows = []
            for size_item in sizes:
                if isinstance(size_item, dict):
                    rows.append((self._get(size_item, "size", "size_name"), self._get(size_item, "quantity")))
            if rows:
                return rows
        return [(self._get(item, "size", "size_name"), self._get(item, "quantity"))]

    def _get(self, data: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    def _int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _decimal(self, value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0").replace(",", ""))
        except InvalidOperation:
            return Decimal("0")

    async def _limited(
        self,
        name: str,
        limit: int,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        async with _get_limiter(name, limit):
            return await factory()
