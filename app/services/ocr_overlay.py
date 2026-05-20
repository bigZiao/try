from typing import Any

from app.models.receipt import Receipt
from app.services.receipt_cropper import ReceiptCropService


class OcrOverlayService:
    HEADER_KEYWORDS = ReceiptCropService.HEADER_KEYWORDS
    SUMMARY_KEYWORDS = ReceiptCropService.FOOTER_KEYWORDS
    EXCLUDED_KEYWORDS = {
        "客户",
        "店员",
        "开单",
        "日期",
        "电话",
        "地址",
        "银行",
        "账号",
        "扫码",
        "二维码",
        "电子小票",
        "备注",
        "提醒",
        "程序",
    }
    SIZE_KEYWORDS = {"均码", "均", "小", "中", "大", "s", "m", "l", "xl", "xxl", "xxxl"}
    COLOR_KEYWORDS = {"色", "白", "黑", "红", "蓝", "绿", "黄", "粉", "紫", "灰", "杏", "卡其", "混"}

    def __init__(self) -> None:
        self.crop_service = ReceiptCropService()

    def key_overlay(self, receipt: Receipt, scope: str = "key") -> dict[str, Any]:
        image_info = self.crop_service.key_image_info(receipt)
        crop_box = image_info.get("crop_box")
        if not isinstance(crop_box, dict):
            crop_box = {
                "left": 0,
                "top": 0,
                "right": image_info.get("source_image_width") or image_info.get("image_width") or 0,
                "bottom": image_info.get("source_image_height") or image_info.get("image_height") or 0,
            }

        blocks = self._overlay_blocks(receipt.ocr_json or {}, crop_box, scope=scope)
        return {
            "receipt_id": receipt.id,
            "view": "key",
            "scope": scope,
            "image_url": f"/api/v1/receipts/{receipt.id}/key-image",
            "image_width": image_info.get("image_width"),
            "image_height": image_info.get("image_height"),
            "source_image_width": image_info.get("source_image_width"),
            "source_image_height": image_info.get("source_image_height"),
            "crop_source": image_info.get("source"),
            "crop_box": crop_box,
            "blocks": blocks,
        }

    def _overlay_blocks(self, ocr_json: dict[str, Any], crop_box: dict[str, int], scope: str) -> list[dict[str, Any]]:
        words_result = ocr_json.get("words_result")
        if not isinstance(words_result, list):
            return []

        crop_left = int(crop_box["left"])
        crop_top = int(crop_box["top"])
        crop_right = int(crop_box["right"])
        crop_bottom = int(crop_box["bottom"])

        overlay_blocks: list[dict[str, Any]] = []
        for index, block in enumerate(words_result):
            if not isinstance(block, dict):
                continue
            location = block.get("location")
            if not isinstance(location, dict):
                continue

            try:
                left = int(location["left"])
                top = int(location["top"])
                width = int(location["width"])
                height = int(location["height"])
            except (KeyError, TypeError, ValueError):
                continue

            right = left + width
            bottom = top + height
            if not self._intersects(left, top, right, bottom, crop_left, crop_top, crop_right, crop_bottom):
                continue

            text = str(block.get("words") or "")
            role = self._role(text)
            if scope == "key" and not self._is_key_text(text, role):
                continue

            rel_left = max(0, left - crop_left)
            rel_top = max(0, top - crop_top)
            rel_right = min(crop_right - crop_left, right - crop_left)
            rel_bottom = min(crop_bottom - crop_top, bottom - crop_top)
            rel_width = max(1, rel_right - rel_left)
            rel_height = max(1, rel_bottom - rel_top)

            overlay_blocks.append(
                {
                    "block_index": block.get("block_index", index),
                    "text": text,
                    "confidence": self._confidence(block),
                    "left": rel_left,
                    "top": rel_top,
                    "width": rel_width,
                    "height": rel_height,
                    "source_left": left,
                    "source_top": top,
                    "source_width": width,
                    "source_height": height,
                    "role": role,
                }
            )

        overlay_blocks.sort(key=lambda block: (block["top"], block["left"]))
        return overlay_blocks

    def _role(self, text: str) -> str:
        if self._contains_keyword(text, self.HEADER_KEYWORDS):
            return "header"
        if self._contains_keyword(text, self.SUMMARY_KEYWORDS):
            return "summary"
        return "item"

    def _is_key_text(self, text: str, role: str) -> bool:
        normalized = text.lower().replace(" ", "")
        if not normalized:
            return False
        if self._contains_keyword(normalized, self.EXCLUDED_KEYWORDS):
            return False
        if role in {"header", "summary"}:
            return True
        if any(keyword in normalized for keyword in self.SIZE_KEYWORDS):
            return True
        if any(keyword in normalized for keyword in self.COLOR_KEYWORDS):
            return True
        if any(char.isdigit() for char in normalized):
            return True
        return False

    def _confidence(self, block: dict[str, Any]) -> float | None:
        probability = block.get("probability")
        if isinstance(probability, dict):
            value = probability.get("average")
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        value = block.get("confidence")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _contains_keyword(self, text: str, keywords: set[str]) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(keyword.lower() in normalized for keyword in keywords)

    def _intersects(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        crop_left: int,
        crop_top: int,
        crop_right: int,
        crop_bottom: int,
    ) -> bool:
        return right > crop_left and left < crop_right and bottom > crop_top and top < crop_bottom
