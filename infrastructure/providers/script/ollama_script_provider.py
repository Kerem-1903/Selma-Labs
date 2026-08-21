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

        language_instruction = f" Please write it in {language}." if language else " Please write it in English."

        prompt = (
            f"Write a {target_duration_seconds}-second engaging YouTube Shorts script about: '{topic}'."
            f" Only output the raw spoken narration text. No stage directions, no markdown, no quotes, no preamble."
            f"{language_instruction}"
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

                    return Script(
                        topic=topic,
                        narration=narration,
                        target_duration_seconds=target_duration_seconds,
                    )
        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise ProviderError(f"Could not connect to Ollama at {self.api_url}: {e}")
        except TimeoutError:
             raise ProviderTimeoutError(f"Ollama request timed out after 60 seconds.")
