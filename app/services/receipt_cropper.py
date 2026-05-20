from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.models.receipt import Receipt
from app.services.image_preprocessor import ImagePreprocessService


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
        self.image_preprocessor = ImagePreprocessService()

    def key_image_path(self, receipt: Receipt) -> Path:
        return Path(self.key_image_info(receipt)["path"])

    def key_image_info(self, receipt: Receipt) -> dict[str, Any]:
        source_path = self.image_preprocessor.prepare_for_ocr(Path(receipt.image_path))
        target_dir = self.settings.crop_image_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{receipt.id}_items.jpg"

        crop_box = self._compute_crop_box(receipt.ocr_json or {})

        try:
            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                width, height = image.size
                if crop_box is None:
                    return self._image_info(
                        path=source_path,
                        crop_box=(0, 0, width, height),
                        image_width=width,
                        image_height=height,
                        source_width=width,
                        source_height=height,
                        source="fallback_original",
                    )

                left, top, right, bottom = self._clamp_box(crop_box, width, height)
                if right - left < 80 or bottom - top < 80:
                    return self._image_info(
                        path=source_path,
                        crop_box=(0, 0, width, height),
                        image_width=width,
                        image_height=height,
                        source_width=width,
                        source_height=height,
                        source="fallback_original",
                    )

                if not (
                    target_path.exists()
                    and source_path.exists()
                    and target_path.stat().st_mtime >= source_path.stat().st_mtime
                ):
                    image.crop((left, top, right, bottom)).save(target_path, format="JPEG", quality=94, optimize=True)
                return self._image_info(
                    path=target_path,
                    crop_box=(left, top, right, bottom),
                    image_width=right - left,
                    image_height=bottom - top,
                    source_width=width,
                    source_height=height,
                    source="ocr_blocks",
                )
        except (UnidentifiedImageError, OSError):
            return self._image_info(
                path=source_path,
                crop_box=None,
                image_width=None,
                image_height=None,
                source_width=None,
                source_height=None,
                source="fallback_original",
            )

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
            text = str(block.get("words") or "")
            blocks.append(
                {
                    "block_index": block.get("block_index", index),
                    "text": text,
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
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

    def _image_info(
        self,
        path: Path,
        crop_box: tuple[int, int, int, int] | None,
        image_width: int | None,
        image_height: int | None,
        source_width: int | None,
        source_height: int | None,
        source: str,
    ) -> dict[str, Any]:
        return {
            "path": path,
            "crop_box": self._box_to_dict(crop_box),
            "image_width": image_width,
            "image_height": image_height,
            "source_image_width": source_width,
            "source_image_height": source_height,
            "source": source,
        }

    def _box_to_dict(self, box: tuple[int, int, int, int] | None) -> dict[str, int] | None:
        if box is None:
            return None
        left, top, right, bottom = box
        return {"left": left, "top": top, "right": right, "bottom": bottom}
