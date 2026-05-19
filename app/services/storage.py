from pathlib import Path
from hashlib import sha256
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings


class ImageStorageService:
    async def save_upload(self, file: UploadFile) -> tuple[Path, str]:
        settings = get_settings()
        settings.upload_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(file.filename or "").suffix or ".jpg"
        safe_name = f"{uuid4().hex}{suffix.lower()}"
        target = settings.upload_dir / safe_name
        digest = sha256()

        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)

        return target, digest.hexdigest()
