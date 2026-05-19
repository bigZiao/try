import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from app.adapters.llm import get_llm_adapter
from app.adapters.ocr import get_ocr_adapter
from app.adapters.vision_llm import get_vision_llm_adapter
from app.services.normalizer import ReceiptNormalizer
from app.services.rule_engine import RuleEngine


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def final_result(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("final_json") or payload.get("corrected_json") or payload.get("structured_json") or {}


async def run_standard_pipeline(ocr_json: dict[str, Any]) -> dict[str, Any]:
    llm = get_llm_adapter()
    normalizer = ReceiptNormalizer()
    rules = RuleEngine()

    structured_json = normalizer.normalize(await llm.structure_receipt(ocr_json))
    first_errors = rules.validate(structured_json)

    corrected_json = None
    final_json = structured_json
    validation_errors = first_errors
    status = "ready_for_review" if not first_errors else "need_review"

    if first_errors:
        corrected_json = normalizer.normalize(await llm.correct_receipt(structured_json, first_errors, ocr_json))
        second_errors = rules.validate(corrected_json)
        validation_errors = second_errors
        final_json = corrected_json if not second_errors else structured_json
        status = "ready_for_review" if not second_errors else "need_review"

    return {
        "status": status,
        "structured_json": structured_json,
        "first_validation_errors": first_errors,
        "corrected_json": corrected_json,
        "final_json": final_json,
        "validation_errors": validation_errors,
    }


async def run_vision_pipeline(image_path: Path, ocr_json: dict[str, Any], reason: str) -> dict[str, Any]:
    llm = get_llm_adapter()
    vision_llm = get_vision_llm_adapter()
    normalizer = ReceiptNormalizer()
    rules = RuleEngine()

    structured_json = normalizer.normalize(await vision_llm.structure_receipt(image_path, ocr_json, reason))
    first_errors = rules.validate(structured_json)

    corrected_json = None
    final_json = structured_json
    validation_errors = first_errors
    status = "ready_for_review" if not first_errors else "need_review"

    if first_errors:
        corrected_json = normalizer.normalize(await llm.correct_receipt(structured_json, first_errors, ocr_json))
        second_errors = rules.validate(corrected_json)
        validation_errors = second_errors
        final_json = corrected_json if not second_errors else structured_json
        status = "ready_for_review" if not second_errors else "need_review"

    return {
        "status": status,
        "structured_json": structured_json,
        "first_validation_errors": first_errors,
        "corrected_json": corrected_json,
        "final_json": final_json,
        "validation_errors": validation_errors,
    }


def should_run_vision(standard_payload: dict[str, Any]) -> bool:
    result = final_result(standard_payload)
    return bool(
        standard_payload.get("first_validation_errors")
        or standard_payload.get("validation_errors")
        or result.get("need_review") is True
        or result.get("parse_status") == "partial"
    )


def append_result_rows(sheet, file_name: str, stage: str, payload: dict[str, Any]) -> None:
    data = final_result(payload)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []

    if not items:
        sheet.append([
            file_name,
            stage,
            payload.get("status"),
            data.get("parse_status"),
            data.get("need_review"),
            data.get("merchant_name"),
            data.get("order_date"),
            data.get("customer_name"),
            None,
            None,
            None,
            None,
            None,
            None,
            summary.get("total_quantity"),
            summary.get("total_amount"),
            json.dumps(data.get("warnings"), ensure_ascii=False),
            json.dumps(payload.get("validation_errors"), ensure_ascii=False),
        ])
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        rows = expand_size_rows(item)
        for size, quantity in rows:
            sheet.append([
                file_name,
                stage,
                payload.get("status"),
                data.get("parse_status"),
                data.get("need_review"),
                data.get("merchant_name"),
                data.get("order_date"),
                data.get("customer_name"),
                item.get("style_no"),
                item.get("product_name"),
                item.get("color"),
                size,
                quantity,
                item.get("unit_price"),
                summary.get("total_quantity"),
                summary.get("total_amount"),
                json.dumps(data.get("warnings"), ensure_ascii=False),
                json.dumps(payload.get("validation_errors"), ensure_ascii=False),
            ])


def expand_size_rows(item: dict[str, Any]) -> list[tuple[Any, Any]]:
    sizes = item.get("sizes")
    if isinstance(sizes, dict):
        return [(size, quantity) for size, quantity in sizes.items()]
    if isinstance(sizes, list):
        rows = []
        for value in sizes:
            if isinstance(value, dict):
                rows.append((value.get("size") or value.get("size_name"), value.get("quantity")))
        if rows:
            return rows
    return [(item.get("size"), item.get("quantity"))]


def export_excel(output_path: Path, results: list[dict[str, Any]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "bill_items"
    sheet.append([
        "file",
        "stage",
        "status",
        "parse_status",
        "need_review",
        "merchant_name",
        "order_date",
        "customer_name",
        "style_no",
        "product_name",
        "color",
        "size",
        "quantity",
        "unit_price",
        "bill_total_quantity",
        "bill_total_amount",
        "warnings",
        "validation_errors",
    ])
    for result in results:
        append_result_rows(sheet, result["file"], result["stage"], result["payload"])
    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 60)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run standard OCR+LLM first, then Doubao vision only for difficult receipts.")
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--first-difficult-only", action="store_true")
    args = parser.parse_args()

    ocr = get_ocr_adapter()
    results: list[dict[str, Any]] = []
    difficult_found = False

    for file_name in args.files:
        image_path = args.image_dir / file_name
        stem = image_path.stem
        receipt_dir = args.output_dir / stem
        print(f"OCR {file_name}")
        ocr_json = await ocr.recognize(image_path)
        dump_json(receipt_dir / "ocr.json", ocr_json)

        print(f"Standard pipeline {file_name}")
        standard_payload = await run_standard_pipeline(ocr_json)
        dump_json(receipt_dir / "standard.parsed.json", standard_payload)
        results.append({"file": file_name, "stage": "standard", "payload": standard_payload})

        if should_run_vision(standard_payload) and (not args.first_difficult_only or not difficult_found):
            difficult_found = True
            reason = "常规 OCR+第一轮大模型结果存在规则错误、need_review 或 partial，需要结合原图重新解析整张票据表格。"
            print(f"Vision difficult pipeline {file_name}")
            vision_payload = await run_vision_pipeline(image_path, ocr_json, reason)
            dump_json(receipt_dir / "vision.parsed.json", vision_payload)
            results.append({"file": file_name, "stage": "vision_difficult", "payload": vision_payload})

    export_excel(args.output_dir / "difficult_receipts_result.xlsx", results)
    print(args.output_dir / "difficult_receipts_result.xlsx")


if __name__ == "__main__":
    asyncio.run(main())
