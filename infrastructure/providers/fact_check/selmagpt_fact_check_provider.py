import aiohttp
import logging
import json
from typing import List, Optional
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.value_objects.fact_check_report import FactCheckReport
from core.domain.value_objects.fact_source import FactSource
from core.domain.exceptions import ProviderError

logger = logging.getLogger(__name__)

class SelmaGPTFactCheckProvider(FactCheckPort):
    """
    Verifies facts using the local SelmaGPT model via an OpenAI-compatible endpoint.
    """
    def __init__(self, api_url: str = "http://localhost:8001/v1/chat/completions", model: str = "SelmaGPT-v1", timeout_seconds: float = 45.0, max_retries: int = 2):
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @property
    def provider_identity(self) -> str:
        return f"SelmaGPTFactCheckProvider({self.model})"

    async def verify(self, *, topic: str, script_text: str, sources: list[FactSource]) -> FactCheckReport:
        logger.info(f"Verifying facts via SelmaGPT...")

        system_prompt = (
            "You are a rigorous professional fact-checker. Evaluate the provided text for factual accuracy. "
            "Identify any factual errors, false claims, or highly misleading statements. "
            "IMPORTANT: Your response MUST be valid JSON matching this schema exactly:\n"
            "{\n"
            '  "is_accurate": true,\n'

            '  "identified_errors": ["Error 1 description if any", "Error 2 description if any"],\n'
            '  "suggestions": ["Suggestion 1", "Suggestion 2"]\n'
            "}\n"
            "Set is_accurate to false ONLY if there are blatant, objective falsehoods. "
            "Only output the JSON object, nothing else."
        )

        user_content = f"Text to verify:\n\n{script_text}"
        context = '\n'.join([s.content for s in sources])
        if context:
            user_content += f"\n\nContext to consider:\n{context}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "max_tokens": 1024
        }

        retries = 0
        while retries <= self.max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, json=payload, timeout=self.timeout_seconds) as response:
                        if response.status != 200:
                            err_text = await response.text()
                            logger.error(f"SelmaGPT fact-check error: {err_text}")
                            raise ProviderError(f"SelmaGPT Fact Check API returned {response.status}")

                        data = await response.json()
                        content = data["choices"][0]["message"]["content"].strip()

                        # Clean up potential markdown formatting from LLM
                        if content.startswith("```json"):
                            content = content.split("```json", 1)[1]
                        if content.startswith("```"):
                            content = content.split("```", 1)[1]
                        if content.endswith("```"):
                            content = content.rsplit("```", 1)[0]
                        content = content.strip()

                        parsed_json = json.loads(content)

                        return FactCheckReport(
                            is_accurate=parsed_json.get("is_accurate", True),
                            identified_errors=parsed_json.get("identified_errors", []),
                            suggestions=parsed_json.get("suggestions", []),
                            confidence_score=float(parsed_json.get("confidence_score", 1.0)),
                        )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse SelmaGPT JSON response: {e}")
                retries += 1
                if retries > self.max_retries:
                    raise ProviderError("SelmaGPT returned invalid JSON for fact checking.") from e
            except Exception as e:
                logger.error(f"SelmaGPT fact checking failed: {e}")
                retries += 1
                if retries > self.max_retries:
                    raise ProviderError(f"SelmaGPT fact checking failed after {self.max_retries} retries: {e}") from e
