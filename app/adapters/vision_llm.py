from abc import ABC, abstractmethod
from base64 import b64encode
from pathlib import Path
from typing import Any

import httpx

from app.adapters.llm import DeepSeekLLMAdapter, parse_json_content
from app.core.config import get_settings
from app.prompts.vision_first_round_prompt import render_vision_first_round_prompt


class VisionLLMAdapter(ABC):
    @abstractmethod
    async def structure_receipt(
        self,
        image_path: Path,
        ocr_json: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockVisionLLMAdapter(VisionLLMAdapter):
    async def structure_receipt(
        self,
        image_path: Path,
        ocr_json: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "parse_status": "mock_vision",
            "merchant_name": "mock vision merchant",
            "customer_name": None,
            "items": [],
            "summary": {},
            "payments": [],
            "warnings": ["Mock vision result. Configure a vision-capable provider for real use."],
            "confidence": 0,
            "confidence_reason": "mock",
            "need_review": True,
        }


class OpenAICompatibleVisionLLMAdapter(VisionLLMAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def structure_receipt(
        self,
        image_path: Path,
        ocr_json: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.vision_llm_api_key:
            raise RuntimeError("VISION_LLM_API_KEY is missing")

        prompt = render_vision_first_round_prompt(ocr_json, reason)
        image_b64 = b64encode(image_path.read_bytes()).decode("ascii")
        image_url = f"data:image/{image_path.suffix.lstrip('.').lower() or 'jpeg'};base64,{image_b64}"

        payload = {
            "model": self.settings.vision_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你只输出严格 JSON，不输出 Markdown 或解释文字。",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.vision_llm_api_key}",
            "Content-Type": "application/json",
        }
        base_url = self.settings.vision_llm_base_url.rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"].get("content") or ""
        return parse_json_content(content)


class TextFallbackVisionLLMAdapter(VisionLLMAdapter):
    async def structure_receipt(
        self,
        image_path: Path,
        ocr_json: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await DeepSeekLLMAdapter().structure_receipt(ocr_json)


def get_vision_llm_adapter() -> VisionLLMAdapter:
    settings = get_settings()
    provider = settings.vision_llm_provider.lower()
    if provider in {"openai_compatible", "openai", "vision", "doubao", "ark", "volcengine"}:
        return OpenAICompatibleVisionLLMAdapter()
    if provider == "text_fallback":
        return TextFallbackVisionLLMAdapter()
    return MockVisionLLMAdapter()
