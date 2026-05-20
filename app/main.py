from html import escape
from typing import Any

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

import app.models  # noqa: F401
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.batches import router as batches_router
from app.api.v1.receipts import router as receipts_router
from app.api.v1.tasks import router as tasks_router
from app.core.bootstrap import ensure_dev_sqlite_schema
from app.core.database import Base, SessionLocal, engine
from app.models.provider_call_log import ProviderCallLog
from app.models.receipt import Receipt
from app.models.receipt_batch import ReceiptBatch
from app.models.receipt_task import ReceiptTask
from app.services.pipeline import ReceiptPipelineService


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    ensure_dev_sqlite_schema()

    app = FastAPI(title="Clothing Wholesale Receipt OCR Backend MVP")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(batches_router, prefix="/api/v1")
    app.include_router(receipts_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")

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

    @app.post("/debug/receipts/{receipt_id}/fields")
    def debug_update_fields(
        receipt_id: int,
        merchant_name: str = Form(""),
        order_date: str = Form(""),
        customer_name: str = Form(""),
        total_quantity: str = Form(""),
        total_amount: str = Form(""),
    ) -> RedirectResponse:
        with SessionLocal() as db:
            service = ReceiptPipelineService(db)
            service.update_review_fields(
                receipt_id,
                {
                    "merchant_name": _none_if_blank(merchant_name),
                    "order_date": _none_if_blank(order_date),
                    "customer_name": _none_if_blank(customer_name),
                },
                {
                    "total_quantity": _int_or_none(total_quantity),
                    "total_amount": _none_if_blank(total_amount),
                },
            )
        return RedirectResponse(url=f"/debug/receipts/{receipt_id}", status_code=303)

    @app.post("/debug/receipts/{receipt_id}/items")
    def debug_add_item(
        receipt_id: int,
        style_no: str = Form(""),
        product_name: str = Form(""),
        color: str = Form(""),
        size: str = Form(""),
        quantity: str = Form("0"),
        unit_price: str = Form("0"),
        subtotal: str = Form("0"),
    ) -> RedirectResponse:
        with SessionLocal() as db:
            ReceiptPipelineService(db).add_review_item(
                receipt_id,
                _item_payload(style_no, product_name, color, size, quantity, unit_price, subtotal),
            )
        return RedirectResponse(url=f"/debug/receipts/{receipt_id}", status_code=303)

    @app.post("/debug/receipts/{receipt_id}/items/{item_index}")
    def debug_update_item(
        receipt_id: int,
        item_index: int,
        style_no: str = Form(""),
        product_name: str = Form(""),
        color: str = Form(""),
        size: str = Form(""),
        quantity: str = Form("0"),
        unit_price: str = Form("0"),
        subtotal: str = Form("0"),
    ) -> RedirectResponse:
        with SessionLocal() as db:
            ReceiptPipelineService(db).update_review_item(
                receipt_id,
                item_index,
                _item_payload(style_no, product_name, color, size, quantity, unit_price, subtotal),
            )
        return RedirectResponse(url=f"/debug/receipts/{receipt_id}", status_code=303)

    @app.post("/debug/receipts/{receipt_id}/items/{item_index}/delete")
    def debug_delete_item(receipt_id: int, item_index: int) -> RedirectResponse:
        with SessionLocal() as db:
            ReceiptPipelineService(db).delete_review_item(receipt_id, item_index)
        return RedirectResponse(url=f"/debug/receipts/{receipt_id}", status_code=303)

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
        tasks = db.query(ReceiptTask).order_by(ReceiptTask.id.desc()).limit(12).all()

    batch_rows = "\n".join(_batch_row(batch) for batch in batches) or _empty_row(6)
    receipt_rows = "\n".join(_receipt_row(receipt) for receipt in receipts) or _empty_row(9)
    task_rows = "\n".join(_task_row(task) for task in tasks) or _empty_row(7)

    return _layout(
        "票据识别后台",
        f"""
<section>
  <h2>最近批次</h2>
  <table>
    <thead><tr><th>ID</th><th>用户</th><th>标题</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
    <tbody>{batch_rows}</tbody>
  </table>
</section>
<section>
  <h2>最近票据</h2>
  <table>
    <thead><tr><th>ID</th><th>批次</th><th>文件名</th><th>状态</th><th>店名</th><th>日期</th><th>金额</th><th>错误</th><th>操作</th></tr></thead>
    <tbody>{receipt_rows}</tbody>
  </table>
</section>
<section>
  <h2>最近任务</h2>
  <table>
    <thead><tr><th>ID</th><th>票据</th><th>状态</th><th>次数</th><th>开始</th><th>结束</th><th>错误</th></tr></thead>
    <tbody>{task_rows}</tbody>
  </table>
</section>
""",
    )


def _debug_receipt_page(receipt_id: int) -> str:
    with SessionLocal() as db:
        receipt = db.get(Receipt, receipt_id)
        logs = (
            db.query(ProviderCallLog)
            .filter(ProviderCallLog.receipt_id == receipt_id)
            .order_by(ProviderCallLog.id.desc())
            .limit(20)
            .all()
            if receipt is not None
            else []
        )

    if receipt is None:
        return _layout("票据不存在", f"<p>没有找到 ID 为 {receipt_id} 的票据。</p>")

    data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    editable = receipt.status != "confirmed"
    item_rows = "\n".join(_debug_item_row(receipt.id, index, item, editable) for index, item in enumerate(items))
    if not item_rows:
        item_rows = '<tr><td colspan="9" class="muted">暂无商品明细</td></tr>'
    log_rows = "\n".join(_call_log_row(log) for log in logs) or _empty_row(8)

    lock_text = '<span class="muted">已确认，final_json 已锁定</span>' if not editable else ""
    confirm_button = (
        f'<form class="inline-form" method="post" action="/debug/receipts/{receipt.id}/confirm">'
        '<button type="submit">通过审核并锁定</button></form>'
        if editable
        else ""
    )

    body = f"""
<p><a href="/">返回后台</a></p>
<div class="review-grid">
  <section class="panel image-panel">
    <h2>原图</h2>
    <img class="receipt-img" src="/api/v1/receipts/{receipt.id}/image" />
  </section>
  <section class="panel">
    <h2>票据 #{receipt.id}</h2>
    <div class="actions">
      {confirm_button}
      {lock_text}
      <a href="/api/v1/receipts/{receipt.id}">JSON</a>
      <a href="/api/v1/receipts/{receipt.id}/export.xlsx">Excel</a>
    </div>
    <table class="meta">
      <tbody>
        <tr><th>状态</th><td><span class="pill {escape(receipt.status)}">{escape(receipt.status)}</span></td></tr>
        <tr><th>文件名</th><td>{escape(receipt.original_filename)}</td></tr>
      </tbody>
    </table>
    {_field_form(receipt.id, data, summary, editable)}
    <h2>商品明细</h2>
    <table>
      <thead><tr><th>#</th><th>款号</th><th>商品名</th><th>颜色</th><th>尺码</th><th>数量</th><th>单价</th><th>小计</th><th>操作</th></tr></thead>
      <tbody>{item_rows}</tbody>
    </table>
    {_add_item_form(receipt.id) if editable else ""}
    <h2>规则错误</h2>
    <pre>{escape(_to_json(receipt.validation_errors or []))}</pre>
    <h2>调用日志</h2>
    <table>
      <thead><tr><th>阶段</th><th>供应商</th><th>模型</th><th>状态</th><th>耗时ms</th><th>tokens</th><th>时间</th><th>错误</th></tr></thead>
      <tbody>{log_rows}</tbody>
    </table>
    <h2>final_json</h2>
    <pre>{escape(_to_json(data))}</pre>
  </section>
</div>
"""
    return _layout(f"票据审核 #{receipt.id}", body)


def _field_form(receipt_id: int, data: dict[str, Any], summary: dict[str, Any], editable: bool) -> str:
    disabled = "" if editable else "disabled"
    return f"""
<form method="post" action="/debug/receipts/{receipt_id}/fields" class="form-grid">
  <label>店名<input name="merchant_name" value="{escape(str(data.get("merchant_name") or ""))}" {disabled}></label>
  <label>日期<input name="order_date" value="{escape(str(data.get("order_date") or ""))}" {disabled}></label>
  <label>客户<input name="customer_name" value="{escape(str(data.get("customer_name") or ""))}" {disabled}></label>
  <label>总数量<input name="total_quantity" value="{escape(str(summary.get("total_quantity") or ""))}" {disabled}></label>
  <label>总金额<input name="total_amount" value="{escape(str(summary.get("total_amount") or ""))}" {disabled}></label>
  <div>{'<button type="submit">保存字段</button>' if editable else ''}</div>
</form>
"""


def _debug_item_row(receipt_id: int, index: int, item: object, editable: bool) -> str:
    if not isinstance(item, dict):
        return f'<tr><td>{index}</td><td colspan="8">{escape(str(item))}</td></tr>'
    values = {
        "style_no": str(_first(item, "style_no", "sku_id", "item_code", "goods_code") or ""),
        "product_name": str(_first(item, "product_name", "sku_name", "spu_name", "goods_name", "name") or ""),
        "color": str(item.get("color") or ""),
        "size": _format_item_size(item),
        "quantity": str(_first(item, "quantity", "total_quantity", "qty") or ""),
        "unit_price": str(item.get("unit_price") or ""),
        "subtotal": str(_first(item, "subtotal", "amount", "total_price") or ""),
    }
    if not editable:
        return f"""
<tr><td>{index}</td><td>{escape(values["style_no"])}</td><td>{escape(values["product_name"])}</td><td>{escape(values["color"])}</td><td>{escape(values["size"])}</td><td>{escape(values["quantity"])}</td><td>{escape(values["unit_price"])}</td><td>{escape(values["subtotal"])}</td><td>已锁定</td></tr>
"""
    return f"""
<tr>
  <form method="post" action="/debug/receipts/{receipt_id}/items/{index}">
    <td>{index}</td>
    <td><input name="style_no" value="{escape(values["style_no"])}"></td>
    <td><input name="product_name" value="{escape(values["product_name"])}"></td>
    <td><input name="color" value="{escape(values["color"])}"></td>
    <td><input name="size" value="{escape(values["size"])}"></td>
    <td><input name="quantity" value="{escape(values["quantity"])}"></td>
    <td><input name="unit_price" value="{escape(values["unit_price"])}"></td>
    <td><input name="subtotal" value="{escape(values["subtotal"])}"></td>
    <td><button type="submit">保存</button></td>
  </form>
</tr>
<tr>
  <td colspan="9">
    <form method="post" action="/debug/receipts/{receipt_id}/items/{index}/delete">
      <button class="danger" type="submit">删除第 {index} 行</button>
    </form>
  </td>
</tr>
"""


def _add_item_form(receipt_id: int) -> str:
    return f"""
<h3>新增商品行</h3>
<form method="post" action="/debug/receipts/{receipt_id}/items" class="item-form">
  <input name="style_no" placeholder="款号">
  <input name="product_name" placeholder="商品名">
  <input name="color" placeholder="颜色">
  <input name="size" placeholder="尺码">
  <input name="quantity" placeholder="数量">
  <input name="unit_price" placeholder="单价">
  <input name="subtotal" placeholder="小计">
  <button type="submit">添加</button>
</form>
"""


def _item_payload(style_no: str, product_name: str, color: str, size: str, quantity: str, unit_price: str, subtotal: str) -> dict[str, Any]:
    return {
        "style_no": _none_if_blank(style_no),
        "product_name": _none_if_blank(product_name),
        "color": _none_if_blank(color),
        "size": _none_if_blank(size),
        "quantity": _int_or_none(quantity) or 0,
        "unit_price": _none_if_blank(unit_price) or "0",
        "subtotal": _none_if_blank(subtotal) or "0",
    }


def _batch_row(batch: ReceiptBatch) -> str:
    return f"""
<tr><td>{batch.id}</td><td>{batch.user_id}</td><td>{escape(batch.title or "")}</td><td><span class="pill {escape(batch.status)}">{escape(batch.status)}</span></td><td>{batch.created_at}</td><td><a href="/api/v1/batches/{batch.id}">JSON</a> · <a href="/api/v1/batches/{batch.id}/export.xlsx">Excel</a></td></tr>
"""


def _receipt_row(receipt: Receipt) -> str:
    data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return f"""
<tr><td>{receipt.id}</td><td>{receipt.batch_id or ""}</td><td>{escape(receipt.original_filename)}</td><td><span class="pill {escape(receipt.status)}">{escape(receipt.status)}</span></td><td>{escape(str(data.get("merchant_name") or ""))}</td><td>{escape(str(data.get("order_date") or ""))}</td><td>{escape(str(summary.get("total_amount") or ""))}</td><td>{len(receipt.validation_errors or [])}</td><td><a href="/debug/receipts/{receipt.id}">审核</a> · <a href="/api/v1/receipts/{receipt.id}">JSON</a> · <a href="/api/v1/receipts/{receipt.id}/image">原图</a></td></tr>
"""


def _task_row(task: ReceiptTask) -> str:
    return f"""
<tr><td>{task.id}</td><td><a href="/debug/receipts/{task.receipt_id}">{task.receipt_id}</a></td><td><span class="pill {escape(task.status)}">{escape(task.status)}</span></td><td>{task.attempts}/{task.max_attempts}</td><td>{task.started_at or ""}</td><td>{task.finished_at or ""}</td><td>{escape((task.last_error or "")[:120])}</td></tr>
"""


def _call_log_row(log: ProviderCallLog) -> str:
    tokens = log.total_tokens if log.total_tokens is not None else ""
    return f"""
<tr><td>{escape(log.stage)}</td><td>{escape(log.provider)}</td><td>{escape(log.model or "")}</td><td><span class="pill {escape(log.status)}">{escape(log.status)}</span></td><td>{log.duration_ms or ""}</td><td>{tokens}</td><td>{log.created_at}</td><td>{escape((log.error_message or "")[:160])}</td></tr>
"""


def _format_item_size(item: dict[str, Any]) -> str:
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


def _layout(title: str, body: str) -> str:
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
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    h2 {{ margin: 22px 0 10px; font-size: 17px; }}
    h3 {{ margin: 14px 0 8px; font-size: 15px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 14px; vertical-align: top; }}
    th {{ background: #f3f4f6; color: #374151; font-weight: 600; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    input {{ box-sizing: border-box; width: 100%; padding: 6px 8px; border: 1px solid #d1d5db; font-size: 13px; }}
    button {{ border: 0; background: #16a34a; color: white; padding: 7px 12px; cursor: pointer; font-size: 14px; }}
    button:hover {{ background: #15803d; }}
    button.danger {{ background: #dc2626; }}
    .muted {{ color: #6b7280; }}
    .actions {{ margin: 12px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .inline-form {{ display: inline-block; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e5e7eb; font-size: 12px; }}
    .ready_for_review, .confirmed, .succeeded, .success {{ background: #dcfce7; color: #166534; }}
    .need_review, .queued, .uploaded, .ocr_processing, .llm_structuring, .running {{ background: #fef3c7; color: #92400e; }}
    .failed, .partial_failed {{ background: #fee2e2; color: #991b1b; }}
    .review-grid {{ display: grid; grid-template-columns: minmax(360px, 0.85fr) minmax(620px, 1.15fr); gap: 18px; align-items: start; }}
    .panel {{ background: white; border: 1px solid #e5e7eb; padding: 16px; }}
    .image-panel {{ position: sticky; top: 12px; }}
    .receipt-img {{ width: 100%; max-height: 82vh; object-fit: contain; background: #111827; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)); gap: 10px; margin: 14px 0; align-items: end; }}
    .form-grid label {{ font-size: 12px; color: #4b5563; }}
    .item-form {{ display: grid; grid-template-columns: repeat(8, minmax(80px, 1fr)); gap: 8px; margin-bottom: 14px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #111827; color: #d1d5db; padding: 12px; overflow: auto; max-height: 420px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class="muted"><a href="/health">健康检查</a> · <a href="/docs">接口文档</a> · <a href="/api/v1/tasks">任务</a> · <a href="/api/v1/tasks/calls">调用日志</a></div>
  </header>
  <main>{body}</main>
</body>
</html>
"""


def _empty_row(colspan: int) -> str:
    return f'<tr><td colspan="{colspan}" class="muted">暂无数据</td></tr>'


def _first(data: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]
    return None


def _none_if_blank(value: str) -> str | None:
    value = value.strip()
    return value or None


def _int_or_none(value: str) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def _to_json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
