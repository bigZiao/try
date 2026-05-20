from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings


class ImagePreprocessService:
    """Create OCR/vision-friendly image copies while preserving original uploads."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def prepare_for_ocr(self, source_path: Path) -> Path:
        if not self.settings.ocr_image_preprocess_enabled:
            return source_path

        target_dir = self.settings.ocr_image_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{source_path.stem}.ocr.jpg"

        if target_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
            return target_path

        try:
            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                image = self._flatten_to_rgb(image)
                image.thumbnail(
                    (self.settings.ocr_image_max_side, self.settings.ocr_image_max_side),
                    Image.Resampling.LANCZOS,
                )
                self._save_jpeg_under_limit(image, target_path)
        except (UnidentifiedImageError, OSError):
            return source_path

        return target_path

    def _flatten_to_rgb(self, image: Image.Image) -> Image.Image:
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, "white")
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
            return background
        return image.convert("RGB")

    def _save_jpeg_under_limit(self, image: Image.Image, target_path: Path) -> None:
        quality = max(1, min(self.settings.ocr_image_jpeg_quality, 95))
        min_quality = 82
        while True:
            image.save(target_path, format="JPEG", quality=quality, optimize=True)
            if target_path.stat().st_size <= self.settings.ocr_image_max_bytes or quality <= min_quality:
                return
            quality -= 4
