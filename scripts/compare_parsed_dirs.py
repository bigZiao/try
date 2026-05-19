import argparse
import json
from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rule_engine import RuleEngine


HEADERS = [
    "file",
    "old_status",
    "new_status",
    "old_rule_errors",
    "new_rule_errors",
    "old_items",
    "new_items",
    "old_second_round",
    "new_second_round",
    "old_need_review",
    "new_need_review",
    "old_total_quantity",
    "new_total_quantity",
    "old_total_amount",
    "new_total_amount",
    "new_error_codes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare parsed OCR result directories.")
    parser.add_argument("old_dir", type=Path)
    parser.add_argument("new_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/parsed_compare.xlsx"))
    args = parser.parse_args()

    rules = RuleEngine()
    old_files = {path.name: path for path in args.old_dir.glob("*.parsed.json")}
    new_files = {path.name: path for path in args.new_dir.glob("*.parsed.json")}

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "compare"
    sheet.append(HEADERS)

    for name in sorted(set(old_files) & set(new_files)):
        old_payload = read_json(old_files[name])
        new_payload = read_json(new_files[name])
        old_final = final_result(old_payload)
        new_final = final_result(new_payload)
        old_errors = rules.validate(old_final)
        new_errors = rules.validate(new_final)

        old_summary = old_final.get("summary") if isinstance(old_final.get("summary"), dict) else {}
        new_summary = new_final.get("summary") if isinstance(new_final.get("summary"), dict) else {}

        sheet.append(
            [
                name,
                old_payload.get("status"),
                new_payload.get("status"),
                len(old_errors),
                len(new_errors),
                len(old_final.get("items") or []),
                len(new_final.get("items") or []),
                old_payload.get("corrected_json") is not None,
                new_payload.get("corrected_json") is not None,
                old_final.get("need_review"),
                new_final.get("need_review"),
                old_summary.get("total_quantity") or old_summary.get("quantity_total"),
                new_summary.get("total_quantity") or new_summary.get("quantity_total"),
                old_summary.get("total_amount"),
                new_summary.get("total_amount"),
                ",".join(error["code"] for error in new_errors),
            ]
        )

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 40)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(args.output)
    print(args.output)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def final_result(payload: dict) -> dict:
    return payload.get("final_json") or payload.get("corrected_json") or payload.get("structured_json") or {}


if __name__ == "__main__":
    main()
