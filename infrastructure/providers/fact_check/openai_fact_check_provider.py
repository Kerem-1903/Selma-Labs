"""OpenAI Responses API fallback for the strict fact-check policy."""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from core.domain.exceptions import ProviderError
from infrastructure.providers.fact_check.nvidia_fact_check_provider import (
    NvidiaFactCheckProvider,
)


class _OpenAICompletionClient:
    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        del temperature
        try:
            response = await self._client.responses.create(
                model=model,
                input=messages,
                max_output_tokens=max_tokens,
            )
            text = response.output_text
        except Exception as error:
            raise ProviderError(f"OpenAI fact-check error: {error}") from error
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("OpenAI fact-check returned empty output.")
        return text.strip()


class OpenAIFactCheckProvider(NvidiaFactCheckProvider):
    """Reuse the vendor-neutral claim/evidence policy with OpenAI transport."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-5.6-sol",
        timeout_seconds: float = 180.0,
        client: Any | None = None,
    ) -> None:
        self._openai_model = model
        super().__init__(
            api_key="transport-owned",
            model=model,
            client=client or _OpenAICompletionClient(api_key, timeout_seconds),
            audit_enabled=True,
            audit_model=model,
        )

    @property
    def provider_identity(self) -> str:
        return f"openai:{self._openai_model}"
