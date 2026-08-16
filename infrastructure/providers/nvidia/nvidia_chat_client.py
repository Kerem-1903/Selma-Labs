from __future__ import annotations

import asyncio
from typing import Any

import httpx

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)


class NvidiaChatClient:
    """Small client for NVIDIA's OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        if not api_key:
            raise ProviderAuthError(
                "NVIDIA API key is missing. Set NVIDIA_API_KEY in your .env file."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport
        self._max_retries = max(0, max_retries)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float = 0.2,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            payload.update(extra_body)
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                if attempt < self._max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                raise ProviderTimeoutError(f"NVIDIA API timed out: {exc}") from exc
            except httpx.RequestError as exc:
                if attempt < self._max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                raise ProviderConnectionError(
                    f"Could not connect to NVIDIA API: {exc}"
                ) from exc

            if response.status_code in {500, 502, 503, 504} and attempt < self._max_retries:
                await self._sleep_before_retry(attempt)
                continue
            break

        if response.status_code in {401, 403}:
            raise ProviderAuthError("NVIDIA API rejected the API key.")
        if response.status_code == 429:
            raise ProviderQuotaExceededError("NVIDIA API rate limit or quota exceeded.")
        if response.is_error:
            # NVIDIA's validation response is safe to surface and is often the
            # only actionable clue for multimodal payload limits.  Keep it
            # bounded so a proxy cannot flood logs with an HTML error page.
            detail = response.text.strip().replace("\n", " ")[:500]
            suffix = f": {detail}" if detail else "."
            raise ProviderError(
                f"NVIDIA API returned an error (status {response.status_code}){suffix}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("NVIDIA API returned an invalid chat response.") from exc

        if not isinstance(content, str) or not content.strip():
            raise ProviderError("NVIDIA API returned empty chat content.")
        return content.strip()

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = self._retry_backoff_seconds * (2**attempt)
        if delay:
            await asyncio.sleep(delay)
