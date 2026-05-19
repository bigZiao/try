from abc import ABC, abstractmethod
from base64 import b64encode
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class OCRAdapter(ABC):
    @abstractmethod
    async def recognize(self, image_path: Path) -> dict[str, Any]:
        raise NotImplementedError


class MockOCRAdapter(OCRAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def recognize(self, image_path: Path) -> dict[str, Any]:
        sidecar = image_path.with_suffix(".ocr.json")
        if sidecar.exists():
            return enrich_ocr_blocks(json.loads(sidecar.read_text(encoding="utf-8")))

        if self.settings.ocr_mock_json_path and self.settings.ocr_mock_json_path.exists():
            return enrich_ocr_blocks(json.loads(self.settings.ocr_mock_json_path.read_text(encoding="utf-8")))

        return enrich_ocr_blocks({
            "provider": "mock",
            "image": image_path.name,
            "words_result": [
                {"words": "单号: MOCK-001"},
                {"words": "客户: 本地测试客户"},
                {"words": "日期: 2026-05-09"},
                {"words": "款号 A100 红色 M 10 20 200"},
                {"words": "款号 A100 红色 L 5 20 100"},
                {"words": "合计 15 300"},
            ],
        })


class BaiduOCRAdapter(OCRAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def recognize(self, image_path: Path) -> dict[str, Any]:
        if not self.settings.baidu_api_key or not self.settings.baidu_secret_key:
            raise RuntimeError("Baidu OCR credentials are missing")

        token = await self._get_access_token()
        image = b64encode(image_path.read_bytes()).decode("ascii")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.settings.baidu_endpoint,
                params={"access_token": token},
                data={"image": image},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return enrich_ocr_blocks(response.json())

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://aip.baidubce.com/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.baidu_api_key,
                    "client_secret": self.settings.baidu_secret_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return payload["access_token"]


def get_ocr_adapter() -> OCRAdapter:
    provider = get_settings().ocr_provider.lower()
    if provider == "baidu":
        return BaiduOCRAdapter()
    return MockOCRAdapter()


def enrich_ocr_blocks(ocr_json: dict[str, Any]) -> dict[str, Any]:
    words_result = ocr_json.get("words_result")
    if not isinstance(words_result, list):
        return ocr_json

    for index, block in enumerate(words_result):
        if isinstance(block, dict) and "block_index" not in block:
            block["block_index"] = index
    return ocr_json
