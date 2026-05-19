import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.llm import get_llm_adapter
from app.adapters.ocr import enrich_ocr_blocks
from app.services.normalizer import ReceiptNormalizer
from app.services.rule_engine import RuleEngine


async def process_file(input_path: Path, output_dir: Path) -> dict[str, Any]:
    ocr_json = enrich_ocr_blocks(json.loads(input_path.read_text(encoding="utf-8")))
    llm = get_llm_adapter()
    rules = RuleEngine()
    normalizer = ReceiptNormalizer()

    structured_json = normalizer.normalize(await llm.structure_receipt(ocr_json))
    first_errors = rules.validate(structured_json)

    corrected_json = None
    second_errors = first_errors
    status = "ready_for_review"

    if first_errors:
        corrected_json = normalizer.normalize(await llm.correct_receipt(structured_json, first_errors, ocr_json))
        second_errors = rules.validate(corrected_json)
        status = "ready_for_review" if not second_errors else "need_review"

    result = {
        "source_file": str(input_path),
        "status": status,
        "ocr_json": ocr_json,
        "structured_json": structured_json,
        "corrected_json": corrected_json,
        "validation_errors": second_errors,
        "final_json": corrected_json if corrected_json is not None and not second_errors else structured_json,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.parsed.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": str(input_path), "status": status, "output": str(output_path)}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Process a directory of Baidu OCR JSON files.")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/parsed_ocr"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("*.json"))
    files = files[args.offset :]
    if args.limit is not None:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No JSON files found in {args.input_dir}")

    for file_path in files:
        output_path = args.output_dir / f"{file_path.stem}.parsed.json"
        if args.skip_existing and output_path.exists():
            print(json.dumps({"file": str(file_path), "status": "skipped", "output": str(output_path)}, ensure_ascii=False))
            continue
        result = await process_file(file_path, args.output_dir)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
