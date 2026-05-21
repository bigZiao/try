from decimal import Decimal, InvalidOperation
from typing import Any


class ReceiptCrossCheckService:
    COMPARE_FIELDS = ["style_no", "product_name", "color", "size", "sizes", "quantity", "unit_price", "subtotal"]

    def compare_items(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        left_items = self._normalize_items(left.get("items"))
        right_items = self._normalize_items(right.get("items"))
        diffs: list[dict[str, Any]] = []

        if len(left_items) != len(right_items):
            diffs.append(
                {
                    "code": "CROSS_CHECK_ITEM_COUNT_MISMATCH",
                    "field": "items.length",
                    "message": "Text and vision lines produced different item counts",
                    "left_value": len(left_items),
                    "right_value": len(right_items),
                }
            )

        for index in range(min(len(left_items), len(right_items))):
            left_item = left_items[index]
            right_item = right_items[index]
            for field in self.COMPARE_FIELDS:
                if left_item.get(field) != right_item.get(field):
                    diffs.append(
                        {
                            "code": "CROSS_CHECK_ITEM_FIELD_MISMATCH",
                            "row": index,
                            "field": field,
                            "message": "Text and vision lines produced different item field values",
                            "left_value": left_item.get(field),
                            "right_value": right_item.get(field),
                        }
                    )

        return {"matched": not diffs, "diffs": diffs}

    def _normalize_items(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [self._normalize_item(item) for item in value if isinstance(item, dict)]

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "style_no": self._text(item.get("style_no")),
            "product_name": self._text(item.get("product_name")),
            "color": self._text(item.get("color")),
            "size": self._size_text(item.get("size")),
            "sizes": self._sizes(item.get("sizes")),
            "quantity": self._number(item.get("quantity")),
            "unit_price": self._money(item.get("unit_price")),
            "subtotal": self._money(item.get("subtotal")),
        }

    def _text(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip().replace(" ", "") or None

    def _size_text(self, value: Any) -> str | None:
        text = self._text(value)
        return text.upper() if text else None

    def _number(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(Decimal(str(value).replace(",", "")))
        except (InvalidOperation, ValueError):
            return None

    def _money(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return str(Decimal(str(value).replace(",", "")).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            return self._text(value)

    def _sizes(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            rows = [{"size": size, "quantity": quantity} for size, quantity in value.items()]
        elif isinstance(value, list):
            rows = [row for row in value if isinstance(row, dict)]
        else:
            return []

        normalized = []
        for row in rows:
            size = self._size_text(row.get("size") or row.get("size_name") or row.get("name"))
            quantity = self._number(row.get("quantity") or row.get("count") or row.get("qty") or row.get("num"))
            normalized.append({"size": size, "quantity": quantity})
        return sorted(normalized, key=lambda row: (row.get("size") or "", row.get("quantity") or 0))
