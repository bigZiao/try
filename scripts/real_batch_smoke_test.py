from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.main import app
from app.models.receipt import Receipt
from app.models.receipt_batch import ReceiptBatch
from app.models.receipt_item import ReceiptItem


def main() -> None:
    image = Path("data/vision_tests/2_21/image.jpg")
    settings = get_settings()
    print("config", {"ocr": settings.ocr_provider, "llm": settings.llm_provider, "model": settings.llm_model})
    print("image_exists", image.exists(), image)

    client = TestClient(app)
    with image.open("rb") as file:
        response = client.post(
            "/api/v1/batches",
            data={"title": "real ocr single test"},
            files=[("files", (image.name, file, "image/jpeg"))],
            headers={"X-User-Id": "1"},
        )
    print("POST /batches", response.status_code)
    print(response.json())

    batch_id = response.json()["id"]
    status_response = client.get(f"/api/v1/batches/{batch_id}", headers={"X-User-Id": "1"})
    print("GET /batches/{id}", status_response.status_code)
    print(status_response.json())

    with SessionLocal() as db:
        batch = db.get(ReceiptBatch, batch_id)
        receipts = db.query(Receipt).filter(Receipt.batch_id == batch_id).order_by(Receipt.id.asc()).all()
        items = (
            db.query(ReceiptItem)
            .join(Receipt, ReceiptItem.receipt_id == Receipt.id)
            .filter(Receipt.batch_id == batch_id)
            .order_by(ReceiptItem.id.asc())
            .all()
        )
        print("db_batch", {"id": batch.id, "status": batch.status, "user_id": batch.user_id})
        for receipt in receipts:
            data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
            print(
                "receipt",
                {
                    "id": receipt.id,
                    "status": receipt.status,
                    "duplicate": receipt.duplicate_status,
                    "errors": receipt.validation_errors,
                    "merchant": data.get("merchant_name"),
                    "summary": data.get("summary"),
                },
            )
        print(
            "db_items",
            [
                {
                    "receipt_id": item.receipt_id,
                    "style_no": item.style_no,
                    "product_name": item.product_name,
                    "color": item.color,
                    "size": item.size,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "subtotal": str(item.subtotal),
                }
                for item in items
            ],
        )


if __name__ == "__main__":
    main()
