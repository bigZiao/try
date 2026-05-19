# Clothing Wholesale Receipt OCR Backend MVP

FastAPI backend for uploading clothing wholesale receipt images, running OCR, structuring with an LLM adapter, validating with rules, storing all intermediate data, confirming final data, and exporting Excel.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Default mode uses SQLite, mock OCR, and mock LLM.

## Environment

```bash
DATABASE_URL=sqlite:///./data/app.db
OCR_PROVIDER=mock
OCR_MOCK_JSON_PATH=
LLM_PROVIDER=mock
UPLOAD_DIR=uploads
```

To test with a saved Baidu OCR response:

```bash
OCR_PROVIDER=mock
OCR_MOCK_JSON_PATH=C:\Users\MRLIAO\Desktop\百度ocr返回\1.json
```

Switching to MySQL later only requires setting `DATABASE_URL`, for example:

```bash
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/receipt_db
```

## Main APIs

- `POST /api/v1/receipts` upload one image, create a receipt task, and process it in the background
- `GET /api/v1/receipts/{receipt_id}` get saved pipeline data
- `POST /api/v1/receipts/{receipt_id}/confirm` submit final confirmed JSON
- `POST /api/v1/receipts/{receipt_id}/vision-rerun` rerun a difficult receipt with image + OCR vision parsing
- `GET /api/v1/receipts/{receipt_id}/export.xlsx` export one receipt
- `GET /api/v1/receipts/export.xlsx` export all confirmed/reviewable receipts
- `POST /api/v1/batches` upload multiple images as one batch
- `GET /api/v1/batches/{batch_id}` get batch progress and receipt statuses
- `GET /api/v1/batches/{batch_id}/export.xlsx` export one batch
- `GET /health`

All receipt and batch APIs accept `X-User-Id`; it defaults to `1` for local MVP testing. The production mini-program should set it from the logged-in owner account.

## Mini-Program Batch Flow

```text
Owner uploads multiple receipt photos
-> backend saves images and creates a receipt batch
-> exact duplicate images are detected with user_id + image_sha256
-> new receipts are processed in background tasks
-> mini-program polls GET /api/v1/batches/{batch_id}
-> owner reviews or confirms receipts
-> export batch Excel
```

Core tables:

- `users`: owner accounts.
- `receipt_batches`: one multi-image upload batch.
- `receipts`: one receipt image and the full OCR/LLM/rule pipeline data.
- `receipt_items`: structured item rows synced from confirmed or review-ready JSON.
- `receipt_runs`: rerun records for difficult receipts.

## DeepSeek

Set the key in your local environment instead of writing it into code or chat:

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-reasoner
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Vision Rerun

Hard receipts can rerun the same pipeline with a vision first round:

```http
POST /api/v1/receipts/{receipt_id}/vision-rerun
```

```json
{
  "apply_result": false,
  "reason": "OCR coordinates are shifted; rebuild the product table from the image."
}
```

The vision first round is followed by the same rule engine and second-round correction flow as the normal pipeline.

Doubao / Volcengine Ark example:

```env
VISION_LLM_PROVIDER=doubao
VISION_LLM_API_KEY=your_ark_api_key
VISION_LLM_MODEL=doubao-1-5-vision-pro-32k-250115
VISION_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

Batch process saved Baidu OCR JSON files:

```bash
python scripts/process_ocr_dir.py C:\Users\MRLIAO\Desktop\百度ocr返回 --output-dir data\parsed_ocr
```
