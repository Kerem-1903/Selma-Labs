import json
import logging
from typing import cast

import aiohttp

from core.domain.exceptions import ProviderError
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.value_objects.fact_check_report import (
    FactCheckReport,
    FactClaim,
    FactVerdict,
)
from core.domain.value_objects.fact_source import FactSource

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
        logger.info("Verifying facts via SelmaGPT...")

        system_prompt = (
            "You are a rigorous professional fact-checker. Use only the supplied source extracts. "
            "Identify every externally verifiable factual claim in the text. "
            "IMPORTANT: Your response MUST be valid JSON matching this schema exactly:\n"
            "{\n"
            '  "claims": [{"claim": "atomic claim", "verdict": "supported|contradicted|uncertain", '
            '"explanation": "reason", "source_urls": ["allowed URL"], '
            '"evidence_quote": "short verbatim source quote"}]\n'
            "}\n"
            "Use uncertain unless a supplied extract directly supports or contradicts the claim. "
            "Only output the JSON object, nothing else."
        )

        user_content = f"Text to verify:\n\n{script_text}"
        context = "\n".join(
            f"SOURCE {source.url}\n{source.extract}" for source in sources
        )
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

                        allowed_urls = {source.url for source in sources}
                        claims: list[FactClaim] = []
                        for raw_claim in parsed_json.get("claims", []):
                            if not isinstance(raw_claim, dict):
                                continue
                            verdict = str(
                                raw_claim.get("verdict") or "uncertain"
                            ).strip().lower()
                            if verdict not in {
                                "supported",
                                "contradicted",
                                "uncertain",
                            }:
                                verdict = "uncertain"
                            source_urls = [
                                str(url)
                                for url in raw_claim.get("source_urls", [])
                                if str(url) in allowed_urls
                            ]
                            evidence_quote = str(
                                raw_claim.get("evidence_quote") or ""
                            ).strip()
                            if verdict == "supported" and (
                                not source_urls or not evidence_quote
                            ):
                                verdict = "uncertain"
                            claim_text = str(raw_claim.get("claim") or "").strip()
                            if claim_text:
                                claims.append(
                                    FactClaim(
                                        claim=claim_text,
                                        verdict=cast(FactVerdict, verdict),
                                        explanation=str(
                                            raw_claim.get("explanation") or ""
                                        ).strip(),
                                        source_urls=source_urls,
                                        evidence_quote=evidence_quote,
                                    )
                                )
                        if not claims:
                            raise ProviderError(
                                "SelmaGPT fact-check response contained no usable claims."
                            )
                        return FactCheckReport.create(
                            claims=claims,
                            sources=sources,
                            provider_used=self.provider_identity,
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
        raise ProviderError("SelmaGPT fact checking exhausted its retry budget.")
