from decimal import Decimal, InvalidOperation
import re
from typing import Any

class RuleEngine:
    def validate(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []

        if not isinstance(data, dict):
            return [{"code": "schema_error", "field": "$", "message": "Receipt result must be an object"}]

        items = data.get("items") or []
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}

        if not isinstance(items, list) or not items:
            errors.append({"code": "items_required", "field": "items", "message": "At least one item is required"})

        if not self._get(data, "merchant_name", "supplier", "商家", "店铺", "店名"):
            errors.append(
                {
                    "code": "merchant_name_required",
                    "field": "merchant_name",
                    "message": "Merchant name is required for each bill",
                }
            )

        calculated_quantity = 0
        calculated_amount = Decimal("0")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({"code": "item_schema_error", "field": f"items.{index}", "message": "Item must be an object"})
                continue

            quantity = self._int(self._get(item, "quantity", "数量"))
            unit_price = self._decimal(self._get(item, "unit_price", "单价"))
            amount = self._decimal(self._get(item, "subtotal", "amount", "小计", "金额"))
            style_no = self._get(
                item,
                "style_no",
                "style_code",
                "sku_code",
                "item_code",
                "item_no",
                "product_code",
                "style_number",
                "款号",
            )
            product_name = self._get(
                item,
                "product_name",
                "sku_name",
                "spu_name",
                "goods_name",
                "item_name",
                "name",
                "商品名称",
                "商品名",
                "名称",
            )
            size = self._get(item, "size", "size_name", "尺码")
            sizes = self._get(item, "sizes", "size_quantities", "尺码明细")
            if not style_no and not product_name:
                errors.append(
                    {
                        "code": "item_identity_required",
                        "field": f"items.{index}",
                        "message": "Each item should have either style_no or product_name",
                    }
                )

            if size is not None and not self._is_valid_size(size):
                errors.append(
                    {
                        "code": "invalid_size",
                        "field": f"items.{index}.size",
                        "message": "Size must be a real size label, not quantity, price, subtotal, or size quantity detail",
                    }
                )

            size_quantity_total = self._size_quantity_total(sizes)
            if size_quantity_total is not None and quantity > 0 and size_quantity_total != quantity:
                errors.append(
                    {
                        "code": "size_quantity_mismatch",
                        "field": f"items.{index}.sizes",
                        "message": f"Size quantities should sum to item quantity ({quantity})",
                    }
                )

            if quantity <= 0:
                errors.append(
                    {
                        "code": "quantity_positive",
                        "field": f"items.{index}.quantity",
                        "message": "Quantity must be greater than 0",
                    }
                )

            if unit_price < 0:
                errors.append(
                    {
                        "code": "unit_price_non_negative",
                        "field": f"items.{index}.unit_price",
                        "message": "Unit price cannot be negative",
                    }
                )

            expected_amount = quantity * unit_price
            if self._money(amount) != self._money(expected_amount):
                errors.append(
                    {
                        "code": "item_amount_mismatch",
                        "field": f"items.{index}.subtotal",
                        "message": f"Item amount should equal quantity * unit_price ({expected_amount})",
                    }
                )

            calculated_quantity += quantity
            calculated_amount += amount

        total_quantity = self._get(
            data,
            "total_quantity",
            "quantity_total",
            "总数量",
            default=self._get(summary, "total_quantity", "quantity_total", "总数量"),
        )
        if total_quantity is not None and self._int(total_quantity) != calculated_quantity:
            errors.append(
                {
                    "code": "total_quantity_mismatch",
                    "field": "summary.total_quantity",
                    "message": f"Total quantity should be {calculated_quantity}",
                }
            )

        total_amount = self._get(data, "total_amount", "总金额", default=self._get(summary, "total_amount", "总金额"))
        if total_amount is not None and self._money(self._decimal(total_amount)) != self._money(calculated_amount):
            errors.append(
                {
                    "code": "total_amount_mismatch",
                    "field": "summary.total_amount",
                    "message": f"Total amount should be {calculated_amount}",
                }
            )

        return errors

    def _money(self, value: Decimal) -> Decimal:
        try:
            return Decimal(value).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")

    def _decimal(self, value: Any) -> Decimal:
        try:
            normalized = str(value or "0").replace(",", "").replace("￥", "").replace("¥", "")
            return Decimal(normalized)
        except InvalidOperation:
            return Decimal("0")

    def _int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _get(self, data: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    def _is_valid_size(self, value: Any) -> bool:
        text = str(value).strip()
        if not text:
            return True
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return False
        if ":" in text or "：" in text or "," in text or "，" in text:
            return False
        valid_sizes = {"均码", "小", "中", "大", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL", "XS", "XXS", "F", "FREE"}
        return text.upper() in valid_sizes or text in valid_sizes

    def _size_quantity_total(self, sizes: Any) -> int | None:
        if not sizes:
            return None
        if isinstance(sizes, dict):
            total = 0
            seen = False
            for value in sizes.values():
                total += self._int(value)
                seen = True
            return total if seen else None
        if isinstance(sizes, list):
            total = 0
            seen = False
            for item in sizes:
                if isinstance(item, dict):
                    total += self._int(self._get(item, "quantity", "数量"))
                    seen = True
            return total if seen else None
        return None
