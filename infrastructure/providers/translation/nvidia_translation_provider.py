from __future__ import annotations

import json

from core.domain.exceptions import SubtitleTranslationError
from core.domain.ports.translation_port import TranslationPort
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient


class NvidiaTranslationProvider(TranslationPort):
    """Translates subtitle lines through NVIDIA's chat endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 30.0,
        client: NvidiaChatClient | None = None,
        max_batch_size: int = 8,
        structure_max_retries: int = 1,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be greater than zero.")
        if structure_max_retries < 0:
            raise ValueError("structure_max_retries must not be negative.")
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self._model = model
        self._max_batch_size = max_batch_size
        self._structure_max_retries = structure_max_retries

    @property
    def provider_identity(self) -> str:
        return f"nvidia:{self._model}"

    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        if not texts:
            return []
        translated: list[str] = []
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            last_error: SubtitleTranslationError | None = None
            for _attempt in range(self._structure_max_retries + 1):
                try:
                    translated.extend(
                        await self._translate_batch(batch, target_language)
                    )
                    last_error = None
                    break
                except SubtitleTranslationError as error:
                    last_error = error
            if last_error is not None:
                raise last_error
        return translated

    async def _translate_batch(
        self,
        texts: list[str],
        target_language: str,
    ) -> list[str]:
        prompt = (
            "You are a professional subtitle translator. "
            f"Translate the following subtitle lines into '{target_language}'.\n"
            "Return only valid JSON with one key named 'translations'. "
            f"Its value must contain exactly {len(texts)} strings in input order. "
            "Do not merge, split, or drop lines.\n"
            f"Input lines:\n{json.dumps(texts, ensure_ascii=False)}"
        )
        raw_text = await self._client.complete(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.1,
        )
        try:
            data = json.loads(self._strip_code_fence(raw_text))
            translations = data.get("translations")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise SubtitleTranslationError(
                f"Failed to parse NVIDIA translation response: {exc}"
            ) from exc
        if not isinstance(translations, list) or len(translations) != len(texts):
            raise SubtitleTranslationError(
                "NVIDIA translation output structure mismatch or invalid length."
            )
        return [str(item) for item in translations]

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        cleaned = text.strip()
        if not cleaned.startswith("```"):
            return cleaned
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
