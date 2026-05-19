from abc import ABC, abstractmethod
import asyncio
from decimal import Decimal
import json
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.prompts.first_round_prompt import render_first_round_prompt
from app.prompts.second_round_prompt import render_second_round_prompt


class LLMAdapter(ABC):
    @abstractmethod
    async def structure_receipt(self, ocr_json: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def correct_receipt(
        self,
        structured_json: dict[str, Any],
        validation_errors: list[dict[str, Any]],
        ocr_json: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockLLMAdapter(LLMAdapter):
    async def structure_receipt(self, ocr_json: dict[str, Any]) -> dict[str, Any]:
        return {
            "parse_status": "success",
            "bill_type": "clothing_wholesale_receipt",
            "merchant_name": "服装批发商",
            "order_date": "2026-05-09",
            "customer_name": "本地测试客户",
            "customer_phone": None,
            "order_no": "MOCK-001",
            "salesperson": None,
            "items": [
                {
                    "style_no": "A100",
                    "product_name": "T恤",
                    "color": "红色",
                    "size": "M",
                    "quantity": 10,
                    "unit_price": "20",
                    "subtotal": "200",
                    "block_indexes": [],
                },
                {
                    "style_no": "A100",
                    "product_name": "T恤",
                    "color": "红色",
                    "size": "L",
                    "quantity": 5,
                    "unit_price": "20",
                    "subtotal": "100",
                    "block_indexes": [],
                },
            ],
            "summary": {
                "total_quantity": 15,
                "total_amount": "300",
            },
            "payments": [],
            "warnings": [],
            "confidence": 0.98,
            "confidence_reason": "Mock result.",
            "need_review": False,
        }

    async def correct_receipt(
        self,
        structured_json: dict[str, Any],
        validation_errors: list[dict[str, Any]],
        ocr_json: dict[str, Any],
    ) -> dict[str, Any]:
        corrected = dict(structured_json)
        items = corrected.get("items") or []

        total_quantity = 0
        total_amount = Decimal("0")
        for item in items:
            quantity = int(item.get("quantity") or 0)
            unit_price = Decimal(str(item.get("unit_price") or "0"))
            amount = quantity * unit_price
            amount_field = "subtotal" if "subtotal" in item else "amount"
            item[amount_field] = str(amount)
            total_quantity += quantity
            total_amount += amount

        if isinstance(corrected.get("summary"), dict):
            corrected["summary"]["total_quantity"] = total_quantity
            corrected["summary"]["total_amount"] = str(total_amount)
        else:
            corrected["total_quantity"] = total_quantity
            corrected["total_amount"] = str(total_amount)
        corrected["warnings"] = corrected.get("warnings") or ["Corrected by mock LLM."]
        return corrected


class HttpLLMAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def structure_receipt(self, ocr_json: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "structure_receipt",
            {
                "prompt": render_first_round_prompt(ocr_json),
                "ocr_json": ocr_json,
            },
        )

    async def correct_receipt(
        self,
        structured_json: dict[str, Any],
        validation_errors: list[dict[str, Any]],
        ocr_json: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._call(
            "correct_receipt",
            {
                "prompt": render_second_round_prompt(ocr_json, structured_json, validation_errors),
                "structured_json": structured_json,
                "validation_errors": validation_errors,
                "ocr_json": ocr_json,
            },
        )
        return response.get("corrected_result", response)

    async def _call(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.llm_api_url:
            raise RuntimeError("LLM_API_URL is missing")

        headers = {}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.settings.llm_api_url,
                json={"model": self.settings.llm_model, "task": task, **payload},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result", data)


class DeepSeekLLMAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def structure_receipt(self, ocr_json: dict[str, Any]) -> dict[str, Any]:
        return await self._chat_json(render_first_round_prompt(ocr_json))

    async def correct_receipt(
        self,
        structured_json: dict[str, Any],
        validation_errors: list[dict[str, Any]],
        ocr_json: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._chat_json(
            render_second_round_prompt(ocr_json, structured_json, validation_errors)
        )
        return response.get("corrected_result", response)

    async def _chat_json(self, prompt: str) -> dict[str, Any]:
        if not self.settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is missing")

        url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你只输出严格 JSON，不输出 Markdown 或解释文字。",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=240) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError("DeepSeek request failed") from last_error

        content = data["choices"][0]["message"].get("content") or ""
        return parse_json_content(content)


def get_llm_adapter() -> LLMAdapter:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    model = settings.llm_model.lower()
    if provider == "deepseek" or model.startswith("deepseek"):
        return DeepSeekLLMAdapter()
    if provider in {"http", "real"}:
        return HttpLLMAdapter()
    return MockLLMAdapter()


def parse_json_content(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if fenced:
            return json.loads(fenced.group(1))

        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])

        raise
