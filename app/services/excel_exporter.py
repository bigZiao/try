from collections.abc import Iterable
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.models.receipt import Receipt


class ExcelExportService:
    HEADERS = [
        "receipt_id",
        "status",
        "ticket_no",
        "receipt_date",
        "supplier",
        "customer",
        "style_no",
        "product_name",
        "color",
        "size",
        "quantity",
        "unit_price",
        "amount",
        "total_quantity",
        "total_amount",
    ]

    def export_receipts(self, receipts: Iterable[Receipt]) -> BytesIO:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "receipts"
        sheet.append(self.HEADERS)

        for receipt in receipts:
            data = receipt.final_json or receipt.corrected_json or receipt.structured_json or {}
            items = data.get("items") or [{}]
            for item in items:
                sheet.append(self._row(receipt, data, item))

        for column in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 32)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    def _row(self, receipt: Receipt, data: dict[str, Any], item: dict[str, Any]) -> list[Any]:
        return [
            receipt.id,
            receipt.status,
            self._get(data, "ticket_no", "order_no", "订单号", "批次"),
            self._get(data, "receipt_date", "order_date", "日期"),
            self._get(data, "supplier", "merchant_name", "商家", "店铺"),
            self._get(data, "customer", "customer_name", "客户", "客户名称"),
            self._get(item, "style_no", "款号"),
            self._get(item, "product_name", "name", "名称", "商品名称"),
            self._get(item, "color", "颜色"),
            self._get(item, "size", "尺码"),
            self._get(item, "quantity", "数量"),
            self._get(item, "unit_price", "单价"),
            self._get(item, "amount", "subtotal", "小计", "金额"),
            self._get(
                data,
                "total_quantity",
                "quantity_total",
                "总数量",
                default=self._get(data.get("summary") or {}, "total_quantity", "quantity_total", "总数量"),
            ),
            self._get(data, "total_amount", "总金额", default=self._get(data.get("summary") or {}, "total_amount", "总金额")),
        ]

    def _get(self, data: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default
