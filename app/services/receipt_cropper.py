from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.models.receipt import Receipt


class ReceiptCropService:
    HEADER_KEYWORDS = {
        "款号",
        "商品编号",
        "商品",
        "编号",
        "article",
        "颜色",
        "尺码",
        "数量",
        "单价",
        "金额",
        "小计",
    }
    FOOTER_KEYWORDS = {
        "合计",
        "总计",
        "数量：",
        "优惠合计",
        "总数",
        "总数量",
        "总金额",
        "现金",
        "支付宝",
        "微信",
        "应收",
        "实收",
        "欠款",
    }
    TABLE_HINT_KEYWORDS = HEADER_KEYWORDS | FOOTER_KEYWORDS

    def __init__(self) -> None:
        self.settings = get_settings()

    def key_image_path(self, receipt: Receipt) -> Path:
        source_path = Path(receipt.image_path)
        target_dir = self.settings.crop_image_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{receipt.id}_items.jpg"

        if target_path.exists() and source_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
            return target_path

        crop_box = self._compute_crop_box(receipt.ocr_json or {})
        if crop_box is None:
            return source_path

        try:
            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                width, height = image.size
                left, top, right, bottom = self._clamp_box(crop_box, width, height)
                if right - left < 80 or bottom - top < 80:
                    return source_path
                image.crop((left, top, right, bottom)).save(target_path, format="JPEG", quality=94, optimize=True)
        except (UnidentifiedImageError, OSError):
            return source_path

        return target_path

    def _compute_crop_box(self, ocr_json: dict[str, Any]) -> tuple[int, int, int, int] | None:
        blocks = self._blocks_with_boxes(ocr_json)
        if not blocks:
            return None

        header_blocks = [block for block in blocks if self._contains_keyword(block["text"], self.HEADER_KEYWORDS)]
        footer_blocks = [block for block in blocks if self._contains_keyword(block["text"], self.FOOTER_KEYWORDS)]
        hint_blocks = [block for block in blocks if self._contains_keyword(block["text"], self.TABLE_HINT_KEYWORDS)]
        if not header_blocks and not hint_blocks:
            return None

        top_anchor = min(header_blocks or hint_blocks, key=lambda block: block["top"])
        top = top_anchor["top"]
        left = min(block["left"] for block in hint_blocks) if hint_blocks else top_anchor["left"]
        right = max(block["right"] for block in hint_blocks) if hint_blocks else top_anchor["right"]

        footer_after_header = [block for block in footer_blocks if block["top"] >= top]
        if footer_after_header:
            first_footer_top = min(block["top"] for block in footer_after_header)
            footer_cluster = [
                block
                for block in footer_after_header
                if block["top"] <= first_footer_top + 120
            ]
            bottom = max(block["bottom"] for block in footer_cluster)
            left = min(left, min(block["left"] for block in footer_cluster))
            right = max(right, max(block["right"] for block in footer_cluster))
        else:
            candidate_rows = [
                block
                for block in blocks
                if block["top"] >= top and block["top"] <= top + 900
            ]
            bottom = max((block["bottom"] for block in candidate_rows), default=top_anchor["bottom"])
            left = min((block["left"] for block in candidate_rows), default=left)
            right = max((block["right"] for block in candidate_rows), default=right)

        padding_left = 55
        padding_right = 180
        padding_top = 55
        padding_bottom = 70
        return (
            left - padding_left,
            top - padding_top,
            right + padding_right,
            bottom + padding_bottom,
        )

    def _blocks_with_boxes(self, ocr_json: dict[str, Any]) -> list[dict[str, Any]]:
        words_result = ocr_json.get("words_result")
        if not isinstance(words_result, list):
            return []

        blocks: list[dict[str, Any]] = []
        for block in words_result:
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
            text = str(block.get("words") or "")
            blocks.append(
                {
                    "text": text,
                    "left": left,
                    "top": top,
                    "right": left + width,
                    "bottom": top + height,
                }
            )
        return blocks

    def _contains_keyword(self, text: str, keywords: set[str]) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(keyword.lower() in normalized for keyword in keywords)

    def _clamp_box(self, box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = box
        return (
            max(0, min(left, width - 1)),
            max(0, min(top, height - 1)),
            max(1, min(right, width)),
            max(1, min(bottom, height)),
        )
