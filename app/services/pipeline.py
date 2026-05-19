from decimal import Decimal, InvalidOperation
from typing import Any
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.adapters.llm import get_llm_adapter
from app.adapters.ocr import get_ocr_adapter
from app.adapters.vision_llm import get_vision_llm_adapter
from app.core.database import SessionLocal
from app.models.receipt_batch import ReceiptBatch
from app.models.receipt_item import ReceiptItem
from app.models.receipt import Receipt
from app.models.receipt_run import ReceiptRun
from app.models.user import User
from app.services.normalizer import ReceiptNormalizer
from app.services.rule_engine import RuleEngine
from app.services.storage import ImageStorageService


class ReceiptPipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = ImageStorageService()
        self.ocr = get_ocr_adapter()
        self.llm = get_llm_adapter()
        self.vision_llm = get_vision_llm_adapter()
        self.rules = RuleEngine()
        self.normalizer = ReceiptNormalizer()

    def ensure_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is not None:
            return user

        if user_id != 1:
            raise HTTPException(status_code=404, detail="User not found")

        user = User(id=1, display_name="默认老板")
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

    async def process_receipt(self, receipt_id: int) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        image_path = Path(receipt.image_path)
        try:
            receipt.status = "ocr_processing"
            self.db.commit()

            receipt.ocr_json = await self.ocr.recognize(image_path)
            receipt.status = "llm_structuring"
            self.db.commit()

            structured_json = self.normalizer.normalize(await self.llm.structure_receipt(receipt.ocr_json))
            result = await self._run_rule_and_correction(structured_json, receipt.ocr_json)
            receipt.structured_json = result["structured_json"]
            receipt.corrected_json = result["corrected_json"]
            receipt.final_json = result["final_json"]
            receipt.validation_errors = result["validation_errors"]
            receipt.status = result["status"]
            if receipt.final_json and receipt.status == "ready_for_review":
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

        structured_json = self.normalizer.normalize(
            await self.vision_llm.structure_receipt(
                image_path=Path(receipt.image_path),
                ocr_json=receipt.ocr_json,
                reason=reason,
            )
        )
        result = await self._run_rule_and_correction(structured_json, receipt.ocr_json)

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
            if receipt.final_json and receipt.status == "ready_for_review":
                self._sync_receipt_items(receipt)

        self.db.commit()
        self.db.refresh(run)
        return run

    async def _run_rule_and_correction(
        self,
        structured_json: dict[str, Any],
        ocr_json: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_structured = self.normalizer.normalize(structured_json)
        first_errors = self.rules.validate(normalized_structured)

        if not first_errors:
            return {
                "structured_json": normalized_structured,
                "corrected_json": None,
                "final_json": normalized_structured,
                "validation_errors": [],
                "status": "ready_for_review",
            }

        corrected_json = self.normalizer.normalize(
            await self.llm.correct_receipt(
                normalized_structured,
                first_errors,
                ocr_json,
            )
        )
        second_errors = self.rules.validate(corrected_json)
        return {
            "structured_json": normalized_structured,
            "corrected_json": corrected_json,
            "final_json": corrected_json if not second_errors else normalized_structured,
            "validation_errors": second_errors,
            "status": "ready_for_review" if not second_errors else "need_review",
        }

    def confirm(self, receipt_id: int, final_json: dict[str, Any]) -> Receipt:
        receipt = self.db.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")

        normalized_json = self.normalizer.normalize(final_json)
        errors = self.rules.validate(normalized_json)
        receipt.final_json = normalized_json
        receipt.validation_errors = errors
        receipt.status = "confirmed" if not errors else "need_review"
        if receipt.status == "confirmed":
            self._sync_receipt_items(receipt)
        self.db.commit()
        self._refresh_batch_status(receipt.batch_id)
        self.db.refresh(receipt)
        return receipt

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
            .filter(Receipt.batch_id == batch_id, Receipt.duplicate_status == "unique")
            .all()
        ]
        if not statuses:
            batch.status = "empty"
        elif all(status in {"ready_for_review", "confirmed"} for status in statuses):
            batch.status = "ready_for_review"
        elif any(status == "failed" for status in statuses):
            batch.status = "partial_failed"
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
