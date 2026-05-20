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

OCR and vision LLM calls use a derived JPEG copy by default. The original upload is still preserved for review and future reprocessing.

```env
OCR_IMAGE_PREPROCESS_ENABLED=true
OCR_IMAGE_DIR=uploads/ocr_images
OCR_IMAGE_MAX_SIDE=2400
OCR_IMAGE_JPEG_QUALITY=92
OCR_IMAGE_MAX_BYTES=4000000
```

Only the derived copy is converted, resized, and compressed. The resize is proportional and does not crop the receipt.

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
- `POST /api/v1/receipts/manual` create a manual receipt without an image; `customer_name` defaults to the current owner
- `GET /api/v1/receipts` list the current owner's receipts; supports `status`, `batch_id`, `source_type`, `start_date`, `end_date`, `merchant_name`, `keyword`, `include_deleted`, `limit`, `offset`
- `DELETE /api/v1/receipts/{receipt_id}` soft-delete one receipt; deleted receipts are excluded from lists and exports by default
- `GET /api/v1/receipts/{receipt_id}` get saved pipeline data
- `GET /api/v1/receipts/{receipt_id}/image` get the original uploaded image for review UI
- `GET /api/v1/receipts/{receipt_id}/key-image` get the cropped key table/payment region for side-by-side review
- `POST /api/v1/receipts/{receipt_id}/confirm` submit final confirmed JSON
- `POST /api/v1/receipts/{receipt_id}/retry` rerun OCR + LLM from the original image after failure
- `PATCH /api/v1/receipts/{receipt_id}/review-fields` update receipt-level fields or summary and rerun rules
- `POST /api/v1/receipts/{receipt_id}/review-items` add one item row and rerun rules
- `PATCH /api/v1/receipts/{receipt_id}/review-items/{item_index}` update one item row and rerun rules
- `DELETE /api/v1/receipts/{receipt_id}/review-items/{item_index}` delete one item row and rerun rules
- `POST /api/v1/receipts/{receipt_id}/vision-rerun` rerun a difficult receipt with image + OCR vision parsing
- `GET /api/v1/receipts/{receipt_id}/export.xlsx` export one receipt
- `GET /api/v1/receipts/export.xlsx` export all confirmed/reviewable receipts
- `POST /api/v1/batches` upload multiple images as one batch
- `GET /api/v1/batches` list the current owner's batches; supports `status`, `limit`, `offset`
- `GET /api/v1/batches/{batch_id}` get batch progress and receipt statuses
- `GET /api/v1/batches/{batch_id}/export.xlsx` export one batch
- `GET /health`

All receipt and batch APIs accept `X-User-Id`; it defaults to `1` for local MVP testing. The production mini-program should set it from the logged-in owner account.

## Mini-Program Batch Flow

```text
Owner uploads multiple receipt photos
-> backend saves images and creates a receipt batch
-> exact duplicate images are detected with user_id + image_sha256
-> new receipts are processed concurrently in background tasks
-> mini-program polls GET /api/v1/batches/{batch_id}
-> owner reviews original image + parsed JSON side by side
-> owner edits and confirms receipts
-> export batch Excel
```

MVP concurrency can be tuned with:

```env
BATCH_PROCESSING_CONCURRENCY=3
OCR_CONCURRENCY=5
LLM_CONCURRENCY=2
VISION_LLM_CONCURRENCY=1
```

The MVP now records receipt work as database-backed tasks before running the in-process worker. This keeps the API shape ready for Redis/RQ/Celery later while already supporting retries, stale-task recovery, and progress inspection:

```env
RECEIPT_TASK_MAX_ATTEMPTS=3
RECEIPT_TASK_STALE_MINUTES=30
```

Useful operational endpoints:

- `GET /api/v1/tasks` list recent receipt tasks
- `POST /api/v1/tasks/recover-stale` reset stale running tasks and enqueue them again
- `GET /api/v1/tasks/calls` list OCR/LLM call logs with status, duration, model, token usage, and error message

Optional token cost estimates can be enabled by setting per-million token prices:

```env
LLM_PROMPT_TOKEN_PRICE_PER_MILLION=0
LLM_COMPLETION_TOKEN_PRICE_PER_MILLION=0
```

Mini-program login starts with:

```http
POST /api/v1/auth/wechat-login
```

Local development uses `WECHAT_LOGIN_PROVIDER=mock`. Production should set `WECHAT_APP_ID` and `WECHAT_APP_SECRET`. The response returns this backend's `user.id`; the mini-program should send it as `X-User-Id` in later receipt and batch requests.

Admin endpoints can be protected with:

```env
ADMIN_TOKEN=change-me
```

Then call admin/task endpoints with `X-Admin-Token`.

The local admin page at `/debug/receipts/{receipt_id}` supports side-by-side image review, receipt-level field edits, item row edits, adding/deleting item rows, and final confirmation. Once a receipt is confirmed, edit APIs reject further changes with `409 Confirmed receipt is locked`.

Core tables:

- `users`: owner accounts.
- `receipt_batches`: one multi-image upload batch.
- `receipts`: one receipt image and the full OCR/LLM/rule pipeline data.
- `receipt_items`: structured item rows synced from confirmed or review-ready JSON.
- `receipt_runs`: rerun records for difficult receipts.
- `receipt_tasks`: queued/running/succeeded/failed processing tasks.
- `provider_call_logs`: OCR/LLM provider calls, duration, model, token usage, and failures.

## Database Migrations

Alembic is configured for production-style schema changes:

```bash
alembic upgrade head
```

`DATABASE_URL` is read from the same environment as the FastAPI app. Local SQLite still keeps the lightweight startup bootstrap for MVP development, but MySQL deployments should use Alembic migrations.

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
