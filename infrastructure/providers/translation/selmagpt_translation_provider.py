import logging

import aiohttp

from core.domain.exceptions import ProviderError
from core.domain.ports.translation_port import TranslationPort

logger = logging.getLogger(__name__)

class SelmaGPTTranslationProvider(TranslationPort):
    """
    Translates text using the local SelmaGPT model via an OpenAI-compatible endpoint.
    """
    def __init__(self, api_url: str = "http://localhost:8001/v1/chat/completions", model: str = "SelmaGPT-v1", timeout_seconds: float = 30.0):
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def provider_identity(self) -> str:
        return f"selmagpt:{self.model}"

    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        """Translate each text in order.

        The port's plural method is the one the subtitle pipeline calls; this
        adapter only implemented the singular form, so the class stayed abstract
        and the ``translation_provider = "selmagpt"`` branch raised
        ``TypeError`` on instantiation. Length and order are preserved.
        """
        return [
            await self.translate_text(text, target_language) for text in texts
        ]

    async def translate_text(self, text: str, target_language: str) -> str:
        logger.info(f"Translating text to {target_language} via SelmaGPT...")

        system_prompt = (
            f"You are a professional translator. Translate the following text perfectly into {target_language}. "
            "Preserve formatting and tone. ONLY output the translated text. Do not add any conversational text."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 1024
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=self.timeout_seconds) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        logger.error(f"SelmaGPT translation error: {err_text}")
                        raise ProviderError(f"SelmaGPT Translation API returned {response.status}")

                    data = await response.json()
                    translation = data["choices"][0]["message"]["content"].strip()
                    return translation
        except Exception as e:
            logger.error(f"SelmaGPT translation failed: {e}")
            raise ProviderError(f"SelmaGPT translation failed: {e}") from e
