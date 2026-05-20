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
            items = data.get("items") if isinstance(data.get("items"), list) else [{}]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for size, quantity in self._expand_size_rows(item):
                    sheet.append(self._row(receipt, data, item, size, quantity))

        for column in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 32)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    def _row(
        self,
        receipt: Receipt,
        data: dict[str, Any],
        item: dict[str, Any],
        size: Any,
        quantity: Any,
    ) -> list[Any]:
        unit_price = self._number(self._get(item, "unit_price", "单价"))
        row_quantity = self._number(quantity)
        amount = (
            unit_price * row_quantity
            if unit_price is not None and row_quantity is not None
            else self._get(item, "amount", "subtotal", "total_price", "小计", "金额")
        )
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}

        return [
            receipt.id,
            receipt.status,
            self._get(data, "ticket_no", "order_no", "订单号", "批次"),
            self._get(data, "receipt_date", "order_date", "日期"),
            self._get(data, "supplier", "merchant_name", "商家", "店铺"),
            self._get(data, "customer", "customer_name", "客户", "客户名称"),
            self._get(item, "style_no", "sku_id", "item_code", "item_no", "product_code", "goods_code", "款号"),
            self._get(item, "product_name", "sku_name", "spu_name", "goods_name", "name", "商品名称"),
            self._get(item, "color", "color_name", "颜色"),
            size,
            quantity,
            self._get(item, "unit_price", "单价"),
            amount,
            self._get(data, "total_quantity", "quantity_total", "总数量", default=self._get(summary, "total_quantity", "quantity_total", "总数量")),
            self._get(data, "total_amount", "总金额", default=self._get(summary, "total_amount", "总金额")),
        ]

    def _expand_size_rows(self, item: dict[str, Any]) -> list[tuple[Any, Any]]:
        sizes = self._get(item, "sizes", "size_quantities", "尺码明细")
        if isinstance(sizes, dict):
            rows = [(size, quantity) for size, quantity in sizes.items() if quantity not in (None, "")]
            if rows:
                return rows

        if isinstance(sizes, list):
            rows = []
            for size_item in sizes:
                if not isinstance(size_item, dict):
                    continue
                size = self._get(size_item, "size", "size_name", "name", "尺码")
                quantity = self._get(size_item, "quantity", "count", "qty", "num", "数量")
                if size not in (None, "") and quantity not in (None, ""):
                    rows.append((size, quantity))
            if rows:
                return rows

        return [
            (
                self._get(item, "size", "size_name", "尺码"),
                self._get(item, "quantity", "total_quantity", "qty", "数量"),
            )
        ]

    def _get(self, data: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    def _number(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None
