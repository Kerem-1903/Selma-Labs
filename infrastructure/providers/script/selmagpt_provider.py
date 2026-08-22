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

        system_prompt = (
            "You are SelmaGPT, a highly specialized AI designed to write viral, engaging, and high-retention YouTube Shorts scripts.\n"
            f"STRATEGY INSTRUCTION: {strategy}"
        )

        # SelmaGPT eğitim verisine sadık (Instruction formatında) prompt hazırlama
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Write a {target_duration_seconds}-second engaging YouTube Shorts script about: '{topic}'. Only output the raw spoken narration text. No stage directions.{language_instruction}"
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

                    return Script(
                        topic=topic,
                        narration=narration,
                        target_duration_seconds=target_duration_seconds,
                    )
        except aiohttp.ClientError as e:
            logger.error(f"SelmaGPT connection error: {e}")
            raise ProviderError(f"Could not connect to SelmaGPT at {self.api_url}: {e}")
        except TimeoutError:
             raise ProviderTimeoutError(f"SelmaGPT request timed out after 60 seconds.")
