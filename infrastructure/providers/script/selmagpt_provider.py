import aiohttp
import logging
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.entities.script import Script
from core.domain.exceptions import ProviderError, ProviderTimeoutError

logger = logging.getLogger(__name__)

class SelmaGPTProvider(ScriptGeneratorPort):
    """
    Bu sağlayıcı (provider), kendi eğittiğimiz SelmaGPT (Fine-Tuned LLaMA-3) modeliyle iletişim kurar.
    Modelin vLLM, Ollama veya Transformers API ile bir endpoint (örn. http://localhost:8000/v1)
    üzerinde çalıştığını varsayar.
    """

    def __init__(self, api_url: str = "http://localhost:8000/v1/chat/completions", model_name: str = "SelmaGPT-v1"):
        self.api_url = api_url
        self.model_name = model_name

    async def generate_script(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str | None = None,
    ) -> Script:

        language_instruction = f" Please write it in {language}." if language else " Please write it in English."

        # Zeka Merkezi (Analytics Strategy) entegrasyonu
        from core.application.services.analytics_strategy_service import analytics_strategy_service
        strategy = await analytics_strategy_service.get_current_strategy()

        # Explicit word bounds logic to fix short-generation bug
        WORDS_PER_MINUTE_TARGET = 150
        expected_words = (target_duration_seconds / 60) * WORDS_PER_MINUTE_TARGET
        min_words = int(expected_words * 0.5)
        max_words = int(expected_words * 1.6)

        system_prompt = (
            "You are SelmaGPT, an elite YouTube Shorts scriptwriter. Your sole purpose is to output highly engaging, viral spoken narration.\n"
            "CRITICAL RULES:\n"
            "1. NO PREAMBLE. NO STAGE DIRECTIONS. NO QUOTES. NO EMOJIS.\n"
            "2. Start with a massive curiosity hook or a shocking statement.\n"
            "3. Keep the pacing extremely fast. Eliminate all filler words.\n"
            "4. End with a strong call to action or a thought-provoking consequence.\n"
            f"STRATEGY INSTRUCTION: {strategy}"
        )

        user_prompt = (
            f"Topic: {topic}\n"
            f"Target duration: {target_duration_seconds} seconds.\n"
            f"Word count constraint: You MUST write exactly between {min_words} and {max_words} words.\n"
            f"Output language: {language_instruction.strip()}\n"
            "Write the raw narration text now, starting immediately with the first spoken word."
        )

        # SelmaGPT eğitim verisine sadık (Instruction formatında) prompt hazırlama
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500,
        }

        logger.info(f"Generating script via SelmaGPT ({self.model_name}) for topic: {topic}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=60) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"SelmaGPT API error: {error_text}")
                        raise ProviderError(f"SelmaGPT API returned status {response.status}")

                    data = await response.json()
                    narration = data["choices"][0]["message"]["content"].strip()

                    return Script.create(
                        topic=topic,
                        full_text=narration,
                        target_duration_seconds=target_duration_seconds,
                        provider_used=f"selmagpt:{self.model_name}"
                    )
        except aiohttp.ClientError as e:
            logger.error(f"SelmaGPT connection error: {e}")
            raise ProviderError(f"Could not connect to SelmaGPT at {self.api_url}: {e}")
        except TimeoutError:
             raise ProviderTimeoutError(f"SelmaGPT request timed out after 60 seconds.")
