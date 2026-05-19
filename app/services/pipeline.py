from typing import Any
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.adapters.llm import get_llm_adapter
from app.adapters.ocr import get_ocr_adapter
from app.adapters.vision_llm import get_vision_llm_adapter
from app.models.receipt import Receipt
from app.models.receipt_run import ReceiptRun
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

    async def create_and_process(self, file: UploadFile) -> Receipt:
        image_path = await self.storage.save_upload(file)
        receipt = Receipt(
            original_filename=file.filename or "upload",
            image_path=str(image_path),
            status="uploaded",
        )
        self.db.add(receipt)
        self.db.commit()
        self.db.refresh(receipt)

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
            self.db.commit()
            self.db.refresh(receipt)
            return receipt
        except Exception as exc:
            receipt.status = "failed"
            receipt.note = str(exc)
            self.db.commit()
            self.db.refresh(receipt)
            raise

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
        self.db.commit()
        self.db.refresh(receipt)
        return receipt
