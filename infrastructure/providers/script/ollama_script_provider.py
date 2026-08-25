import aiohttp
import json
import logging
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.entities.script import Script
from core.domain.exceptions import ProviderError, ProviderTimeoutError, ProviderAuthError

logger = logging.getLogger(__name__)

class OllamaScriptProvider(ScriptGeneratorPort):
    def __init__(self, api_url: str = "http://localhost:11434/api/generate", model: str = "llama3"):
        self.api_url = api_url
        self.model = model

    async def generate_script(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str | None = None,
    ) -> Script:

        # Zeka Merkezi (Analytics Strategy) entegrasyonu
        from core.application.services.analytics_strategy_service import analytics_strategy_service
        strategy = await analytics_strategy_service.get_current_strategy()

        language_instruction = f" Please write it in {language}." if language else " Please write it in English."

        WORDS_PER_MINUTE_TARGET = 150
        expected_words = (target_duration_seconds / 60) * WORDS_PER_MINUTE_TARGET
        min_words = int(expected_words * 0.5)
        max_words = int(expected_words * 1.6)

        prompt = (
            f"You are an elite YouTube Shorts scriptwriter. Your sole purpose is to output highly engaging, viral spoken narration.\n"
            f"Topic: {topic}\n"
            f"Target duration: {target_duration_seconds} seconds.\n"
            f"Word count constraint: You MUST write exactly between {min_words} and {max_words} words.\n"
            f"Output language: {language_instruction.strip()}\n"
            "CRITICAL RULES:\n"
            "1. NO PREAMBLE. NO STAGE DIRECTIONS. NO QUOTES. NO EMOJIS. Output ONLY the raw spoken text.\n"
            "2. Start with a massive curiosity hook or a shocking statement.\n"
            "3. Keep the pacing extremely fast. Eliminate all filler words.\n"
            "4. End with a strong call to action or a thought-provoking consequence.\n"
            f"STRATEGY INSTRUCTION: {strategy}\n"
            "Write the raw narration text now, starting immediately with the first spoken word."
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        logger.info(f"Generating script via Ollama ({self.model}) for topic: {topic}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=60) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama error: {error_text}")
                        raise ProviderError(f"Ollama returned status {response.status}")

                    data = await response.json()
                    narration = data.get("response", "").strip()

                    return Script.create(
                        topic=topic,
                        full_text=narration,
                        target_duration_seconds=target_duration_seconds,
                        provider_used=f"ollama:{self.model}"
                    )
        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise ProviderError(f"Could not connect to Ollama at {self.api_url}: {e}")
        except TimeoutError:
             raise ProviderTimeoutError(f"Ollama request timed out after 60 seconds.")
