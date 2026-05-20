from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

import app.models  # noqa: F401
from app.api.v1.batches import router as batches_router
from app.api.v1.receipts import router as receipts_router
from app.core.bootstrap import ensure_dev_sqlite_schema
from app.core.database import Base, SessionLocal, engine
from app.models.receipt import Receipt
from app.models.receipt_batch import ReceiptBatch
from app.services.pipeline import ReceiptPipelineService


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    ensure_dev_sqlite_schema()

    app = FastAPI(title="Clothing Wholesale Receipt OCR Backend MVP")
    app.include_router(batches_router, prefix="/api/v1")
    app.include_router(receipts_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _debug_page(limit=8)

    @app.get("/debug", response_class=HTMLResponse)
    def debug() -> str:
        return _debug_page(limit=30)

    @app.get("/debug/receipts/{receipt_id}", response_class=HTMLResponse)
    def debug_receipt(receipt_id: int) -> str:
        return _debug_receipt_page(receipt_id)

    @app.post("/debug/receipts/{receipt_id}/confirm")
    def debug_confirm_receipt(receipt_id: int) -> RedirectResponse:
        with SessionLocal() as db:
            receipt = db.get(Receipt, receipt_id)
            if receipt is not None:
                final_json = receipt.final_json or receipt.corrected_json or receipt.structured_json
                if isinstance(final_json, dict):
                    ReceiptPipelineService(db).confirm(receipt_id, final_json)
        return RedirectResponse(url=f"/debug/receipts/{receipt_id}", status_code=303)

    return app


app = create_app()


def _debug_page(limit: int) -> str:
    with SessionLocal() as db:
        batches = db.query(ReceiptBatch).order_by(ReceiptBatch.id.desc()).limit(limit).all()
        receipts = db.query(Receipt).order_by(Receipt.id.desc()).limit(limit * 5).all()

    batch_rows = "\n".join(_batch_row(batch) for batch in batches) or (
        '<tr><td colspan="6" class="muted">暂无批次</td></tr>'
    )
    receipt_rows = "\n".join(_receipt_row(receipt) for receipt in receipts) or (
        '<tr><td colspan="9" class="muted">暂无票据</td></tr>'
    )

    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>票据识别后端调试台</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f6f7f9; color: #1f2937; }}
    header {{ background: #111827; color: white; padding: 22px 28px; }}
    main {{ padding: 22px 28px 40px; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    h2 {{ margin: 26px 0 12px; font-size: 18px; }}
    .muted {{ color: #6b7280; }}
    .links a {{ color: #bfdbfe; margin-right: 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 14px; vertical-align: top; }}
    th {{ background: #f3f4f6; color: #374151; font-weight: 600; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e5e7eb; font-size: 12px; }}
    .ready_for_review, .confirmed {{ background: #dcfce7; color: #166534; }}
    .need_review {{ background: #fef3c7; color: #92400e; }}
    .failed, .partial_failed {{ background: #fee2e2; color: #991b1b; }}
    .processing, .queued, .uploaded, .ocr_processing, .llm_structuring {{ background: #dbeafe; color: #1e40af; }}
    .grid {{ display: grid; grid-template-columns: minmax(320px, 0.9fr) minmax(480px, 1.1fr); gap: 18px; align-items: start; }}
    .panel {{ background: white; border: 1px solid #e5e7eb; padding: 16px; }}
    .receipt-img {{ width: 100%; max-height: 78vh; object-fit: contain; background: #111827; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #111827; color: #d1d5db; padding: 12px; overflow: auto; max-height: 420px; }}
    .actions {{ margin: 12px 0; }}
    .actions a {{ display: inline-block; margin-right: 10px; }}
    .inline-form {{ display: inline-block; margin-right: 10px; }}
    button {{ border: 0; background: #16a34a; color: white; padding: 7px 12px; cursor: pointer; font-size: 14px; }}
    button:hover {{ background: #15803d; }}
  </style>
</head>
<body>
  <header>
    <h1>票据识别后端调试台</h1>
    <div class="muted">用于本地开发联调，不是正式小程序前端。</div>
    <div class="links">
      <a href="/health">健康检查</a>
      <a href="/docs">接口文档</a>
      <a href="/api/v1/receipts/export.xlsx">导出全部 Excel</a>
    </div>
  </header>
  <main>
    <h2>最近批次</h2>
    <table>
      <thead>
        <tr><th>ID</th><th>用户</th><th>标题</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
      </thead>
      <tbody>{batch_rows}</tbody>
    </table>

    <h2>最近票据</h2>
    <table>
      <thead>
        <tr><th>ID</th><th>批次</th><th>文件名</th><th>状态</th><th>店名</th><th>日期</th><th>金额</th><th>错误</th><th>操作</th></tr>
      </thead>
      <tbody>{receipt_rows}</tbody>
    </table>
  </main>
</body>
</html>
"""


def _batch_row(batch: ReceiptBatch) -> str:
    return f"""
<tr>
  <td>{batch.id}</td>
  <td>{batch.user_id}</td>
  <td>{escape(batch.title or "")}</td>
  <td><span class="pill {escape(batch.status)}">{escape(batch.status)}</span></td>
  <td>{batch.created_at}</td>
  <td>
    <a href="/api/v1/batches/{batch.id}">JSON</a>
    · <a href="/api/v1/batches/{batch.id}/export.xlsx">Excel</a>
  </td>
</tr>
"""


def _receipt_row(receipt: Receipt) -> str:
    data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    errors = receipt.validation_errors or []
    return f"""
<tr>
  <td>{receipt.id}</td>
  <td>{receipt.batch_id or ""}</td>
  <td>{escape(receipt.original_filename)}</td>
  <td><span class="pill {escape(receipt.status)}">{escape(receipt.status)}</span></td>
  <td>{escape(str(data.get("merchant_name") or ""))}</td>
  <td>{escape(str(data.get("order_date") or ""))}</td>
  <td>{escape(str(summary.get("total_amount") or ""))}</td>
  <td>{len(errors)}</td>
  <td>
    <a href="/debug/receipts/{receipt.id}">审核</a>
    ·
    <a href="/api/v1/receipts/{receipt.id}">JSON</a>
    · <a href="/api/v1/receipts/{receipt.id}/image">原图</a>
    · <a href="/api/v1/receipts/{receipt.id}/export.xlsx">Excel</a>
  </td>
</tr>
"""


def _debug_receipt_page(receipt_id: int) -> str:
    with SessionLocal() as db:
        receipt = db.get(Receipt, receipt_id)

    if receipt is None:
        return _simple_page("票据不存在", f"<p>没有找到 ID 为 {receipt_id} 的票据。</p>")

    data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    item_rows = "\n".join(_debug_item_row(index, item) for index, item in enumerate(items)) or (
        '<tr><td colspan="9" class="muted">暂无商品明细</td></tr>'
    )
    errors = receipt.validation_errors or []

    body = f"""
<p><a href="/">返回调试台</a></p>
<div class="grid">
  <section class="panel">
    <h2>原图</h2>
    <img class="receipt-img" src="/api/v1/receipts/{receipt.id}/image" />
  </section>
  <section class="panel">
    <h2>票据 #{receipt.id}</h2>
    <div class="actions">
      <form class="inline-form" method="post" action="/debug/receipts/{receipt.id}/confirm">
        <button type="submit">通过审核</button>
      </form>
      <a href="/api/v1/receipts/{receipt.id}">查看 JSON</a>
      <a href="/api/v1/receipts/{receipt.id}/export.xlsx">导出 Excel</a>
      <a href="/docs#/receipts/retry_receipt_api_v1_receipts__receipt_id__retry_post">重试接口</a>
      <a href="/docs#/receipts/confirm_receipt_api_v1_receipts__receipt_id__confirm_post">确认接口</a>
    </div>
    <table>
      <tbody>
        <tr><th>状态</th><td><span class="pill {escape(receipt.status)}">{escape(receipt.status)}</span></td></tr>
        <tr><th>文件名</th><td>{escape(receipt.original_filename)}</td></tr>
        <tr><th>店名</th><td>{escape(str(data.get("merchant_name") or ""))}</td></tr>
        <tr><th>日期</th><td>{escape(str(data.get("order_date") or ""))}</td></tr>
        <tr><th>客户</th><td>{escape(str(data.get("customer_name") or ""))}</td></tr>
        <tr><th>总数量</th><td>{escape(str(summary.get("total_quantity") or ""))}</td></tr>
        <tr><th>总金额</th><td>{escape(str(summary.get("total_amount") or ""))}</td></tr>
      </tbody>
    </table>

    <h2>商品明细</h2>
    <table>
      <thead>
        <tr><th>#</th><th>款号</th><th>商品名</th><th>颜色</th><th>尺码</th><th>数量</th><th>单价</th><th>小计</th><th>操作</th></tr>
      </thead>
      <tbody>{item_rows}</tbody>
    </table>

    <h2>规则错误</h2>
    <pre>{escape(_to_json(errors))}</pre>

    <h2>最终 JSON</h2>
    <pre>{escape(_to_json(data))}</pre>
  </section>
</div>
"""
    return _simple_page(f"票据审核 #{receipt.id}", body)


def _debug_item_row(index: int, item: object) -> str:
    if not isinstance(item, dict):
        return f'<tr><td>{index}</td><td colspan="8">{escape(str(item))}</td></tr>'
    size_text = _format_item_size(item)
    return f"""
<tr>
  <td>{index}</td>
  <td>{escape(str(_first(item, "style_no", "sku_id", "item_code", "goods_code") or ""))}</td>
  <td>{escape(str(_first(item, "product_name", "sku_name", "spu_name", "goods_name", "name") or ""))}</td>
  <td>{escape(str(item.get("color") or ""))}</td>
  <td>{escape(size_text)}</td>
  <td>{escape(str(_first(item, "quantity", "total_quantity", "qty") or ""))}</td>
  <td>{escape(str(item.get("unit_price") or ""))}</td>
  <td>{escape(str(_first(item, "subtotal", "amount", "total_price") or ""))}</td>
  <td><a href="/docs#/receipts/update_review_item_api_v1_receipts__receipt_id__review_items__item_index__patch">修改</a></td>
</tr>
"""


def _format_item_size(item: dict) -> str:
    size = item.get("size") or item.get("size_name")
    if size not in (None, ""):
        return str(size)

    sizes = item.get("sizes") or item.get("size_quantities")
    if isinstance(sizes, dict):
        return "，".join(f"{key}:{value}" for key, value in sizes.items())
    if isinstance(sizes, list):
        parts = []
        for size_item in sizes:
            if not isinstance(size_item, dict):
                continue
            size_name = _first(size_item, "size", "size_name", "name", "尺码")
            quantity = _first(size_item, "quantity", "count", "qty", "num", "数量")
            if size_name not in (None, ""):
                parts.append(f"{size_name}:{quantity}" if quantity not in (None, "") else str(size_name))
        return "，".join(parts)
    return ""


def _simple_page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f6f7f9; color: #1f2937; }}
    header {{ background: #111827; color: white; padding: 18px 28px; }}
    main {{ padding: 22px 28px 40px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 18px 0 10px; font-size: 17px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 14px; vertical-align: top; }}
    th {{ background: #f3f4f6; color: #374151; font-weight: 600; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .muted {{ color: #6b7280; }}
    .grid {{ display: grid; grid-template-columns: minmax(320px, 0.9fr) minmax(480px, 1.1fr); gap: 18px; align-items: start; }}
    .panel {{ background: white; border: 1px solid #e5e7eb; padding: 16px; }}
    .receipt-img {{ width: 100%; max-height: 78vh; object-fit: contain; background: #111827; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #111827; color: #d1d5db; padding: 12px; overflow: auto; max-height: 420px; }}
    .actions {{ margin: 12px 0; }}
    .actions a {{ display: inline-block; margin-right: 10px; }}
    .inline-form {{ display: inline-block; margin-right: 10px; }}
    button {{ border: 0; background: #16a34a; color: white; padding: 7px 12px; cursor: pointer; font-size: 14px; }}
    button:hover {{ background: #15803d; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e5e7eb; font-size: 12px; }}
    .ready_for_review, .confirmed {{ background: #dcfce7; color: #166534; }}
    .need_review {{ background: #fef3c7; color: #92400e; }}
    .failed, .partial_failed {{ background: #fee2e2; color: #991b1b; }}
    .processing, .queued, .uploaded, .ocr_processing, .llm_structuring {{ background: #dbeafe; color: #1e40af; }}
  </style>
</head>
<body>
  <header><h1>{escape(title)}</h1></header>
  <main>{body}</main>
</body>
</html>
"""


def _first(data: dict, *keys: str) -> object:
    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]
    return None


def _to_json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
