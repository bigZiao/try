from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.provider_call_log import ProviderCallLog
from app.core.config import get_settings


class ProviderCallLogger:
    def __init__(self, db: Session, receipt_id: int | None = None, task_id: int | None = None) -> None:
        self.db = db
        self.receipt_id = receipt_id
        self.task_id = task_id
        self.settings = get_settings()

    async def record(
        self,
        provider: str,
        stage: str,
        model: str | None,
        factory: Callable[[], Awaitable[Any]],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        started = perf_counter()
        try:
            result = await factory()
        except Exception as exc:
            self._save(
                provider=provider,
                stage=stage,
                model=model,
                status="failed",
                duration_ms=int((perf_counter() - started) * 1000),
                error_message=str(exc),
                metadata_json=metadata,
            )
            raise

        usage = self._extract_usage(result)
        self._save(
            provider=provider,
            stage=stage,
            model=model,
            status="success",
            duration_ms=int((perf_counter() - started) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            estimated_cost=self._estimate_cost(usage),
            metadata_json=metadata,
        )
        return result

    def _save(self, **kwargs: Any) -> None:
        self.db.add(ProviderCallLog(receipt_id=self.receipt_id, task_id=self.task_id, **kwargs))
        self.db.commit()

    def _extract_usage(self, result: Any) -> dict[str, int | None]:
        if not isinstance(result, dict):
            return {}
        usage = result.get("_usage")
        if not isinstance(usage, dict):
            return {}
        return {
            "prompt_tokens": self._int_or_none(usage.get("prompt_tokens")),
            "completion_tokens": self._int_or_none(usage.get("completion_tokens")),
            "total_tokens": self._int_or_none(usage.get("total_tokens")),
        }

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _estimate_cost(self, usage: dict[str, int | None]) -> str | None:
        prompt_tokens = usage.get("prompt_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or 0
        input_price = self.settings.llm_prompt_token_price_per_million
        output_price = self.settings.llm_completion_token_price_per_million
        if not prompt_tokens and not completion_tokens:
            return None
        if input_price <= 0 and output_price <= 0:
            return None
        cost = prompt_tokens * input_price / 1_000_000 + completion_tokens * output_price / 1_000_000
        return f"{cost:.6f}"
