from typing import Any


class ReceiptNormalizer:
    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        normalized.setdefault("warnings", [])
        normalized.setdefault("payments", [])
        normalized.setdefault("need_review", None)
        normalized.setdefault("confidence", None)
        normalized.setdefault("confidence_reason", None)

        items = normalized.get("items")
        if isinstance(items, list):
            normalized["items"] = [self._normalize_item(item) for item in items]

        return normalized

    def _normalize_item(self, item: Any) -> Any:
        if not isinstance(item, dict):
            return item

        normalized = dict(item)
        self._copy_first(normalized, "style_no", ["style_code", "sku_id", "sku_code", "item_code", "item_no", "product_code", "style_number", "spu_id", "goods_code"])
        self._copy_first(normalized, "product_name", ["name", "sku_name", "spu_name", "item_name", "product_title", "goods_name"])
        self._copy_first(normalized, "quantity", ["total_quantity", "qty"])
        self._copy_first(normalized, "subtotal", ["total_price", "amount", "line_amount"])
        self._normalize_sizes(normalized)
        if normalized.get("sizes") and self._is_aggregate_size(normalized.get("size")):
            normalized["size"] = None
        normalized.setdefault("block_indexes", [])
        return normalized

    def _copy_first(self, data: dict[str, Any], target: str, aliases: list[str]) -> None:
        if data.get(target) not in (None, ""):
            return
        for alias in aliases:
            if data.get(alias) not in (None, ""):
                data[target] = data[alias]
                return

    def _is_aggregate_size(self, value: Any) -> bool:
        if value is None:
            return False
        text = str(value).strip()
        return "/" in text or "\\" in text or "," in text or "，" in text

    def _normalize_sizes(self, item: dict[str, Any]) -> None:
        sizes = item.get("sizes")
        if not isinstance(sizes, list):
            return

        normalized_sizes = []
        for size_item in sizes:
            if not isinstance(size_item, dict):
                normalized_sizes.append(size_item)
                continue

            normalized = dict(size_item)
            self._copy_first(normalized, "quantity", ["count", "qty", "num"])
            normalized_sizes.append(normalized)
        item["sizes"] = normalized_sizes
