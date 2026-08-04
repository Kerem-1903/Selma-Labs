import json
import logging
from typing import List

import anthropic

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    SubtitleTranslationError,
)
from core.domain.ports.translation_port import TranslationPort

logger = logging.getLogger(__name__)


class ClaudeTranslationProvider(TranslationPort):
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-3-5-sonnet-20241022",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ProviderAuthError("Anthropic API key is required.")
        self._model_name = model_name
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    @property
    def provider_identity(self) -> str:
        return f"anthropic:{self._model_name}"

    async def translate_texts(self, texts: List[str], target_language: str) -> List[str]:
        if not texts:
            return []

        prompt = (
            f"You are a professional subtitle translator. Translate the following list of subtitle lines "
            f"into target language '{target_language}'.\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. You MUST return valid JSON.\n"
            f"2. The JSON MUST contain a single key 'translations' holding a list of strings.\n"
            f"3. The 'translations' list MUST contain EXACTLY {len(texts)} items, maintaining exact input order.\n"
            f"4. Do not merge, split, or drop lines.\n\n"
            f"Input lines:\n"
            f"{json.dumps(texts, ensure_ascii=False)}"
        )

        try:
            response = await self._client.messages.create(
                model=self._model_name,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            content_block = response.content[0]
            response_text = getattr(content_block, "text", str(content_block))
            
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            data = json.loads(clean_text.strip())
            translations = data.get("translations")

            if not isinstance(translations, list) or len(translations) != len(texts):
                raise SubtitleTranslationError("Provider output structure mismatch or invalid length.")

            return [str(item) for item in translations]

        except anthropic.AuthenticationError as e:
            raise ProviderAuthError(f"Anthropic authentication failed: {e}") from e
        except anthropic.RateLimitError as e:
            raise ProviderQuotaExceededError(f"Anthropic quota exceeded: {e}") from e
        except anthropic.APITimeoutError as e:
            raise ProviderTimeoutError(f"Anthropic request timed out: {e}") from e
        except json.JSONDecodeError as e:
            raise SubtitleTranslationError(f"Failed to parse provider JSON response: {e}") from e
        except anthropic.APIError as e:
            raise ProviderError(f"Anthropic API error: {e}") from e
        except Exception as e:
            if isinstance(e, (ProviderError, SubtitleTranslationError)):
                raise
            raise ProviderError(f"Unexpected translation provider error: {e}") from e
