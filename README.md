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

- `POST /api/v1/receipts` upload image and run full pipeline
- `GET /api/v1/receipts/{receipt_id}` get saved pipeline data
- `POST /api/v1/receipts/{receipt_id}/confirm` submit final confirmed JSON
- `GET /api/v1/receipts/{receipt_id}/export.xlsx` export one receipt
- `GET /api/v1/receipts/export.xlsx` export all confirmed/reviewable receipts
- `GET /health`

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
