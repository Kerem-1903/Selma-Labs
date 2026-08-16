from __future__ import annotations

import json
import math

from core.domain.entities.script import Script
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.domain.ports.script_rewriter_port import ScriptRewriterPort
from core.domain.value_objects.fact_check_report import FactCheckReport
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient


SYSTEM_PROMPT = """You rewrite narration for short educational vertical videos.
Use only facts directly stated in the supplied source extracts. Remove or replace
every contradicted or uncertain claim. Do not add facts from memory, estimates,
specific numbers, rhetorical factual questions, or unsupported hooks.

Keep the original language, topic, energetic spoken style, and approximate target
word count. Return only the finished narration as plain text. Every factual sentence
must be directly supportable by a verbatim sentence in the supplied extracts.
Open with a short source-supported curiosity hook, use short sentences with distinct
visual beats, and end on the strongest supported fact rather than a generic summary.
If the topic asks why, state the supported cause explicitly. If it asks how, state
the supported mechanism or sequence explicitly. Never pad with invitations or empty
praise such as "let's explore", "yakından bakalım", "keşfedelim", or "this is
fascinating". The first sentence must be no more than 18 words and must contain a
question, contrast, precise number, or consequence. A why-topic needs a later
sentence with an explicit causal connector such as "Çünkü", "Bu yüzden", or
"Because". Use at least three complete sentences. If sources are limited, prefer a
shorter dense draft over filler."""


class NvidiaFactGroundedRewriter(ScriptRewriterPort):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 180.0,
        client: NvidiaChatClient | None = None,
        max_generation_attempts: int = 2,
    ) -> None:
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self._model = model
        self._max_generation_attempts = max(1, max_generation_attempts)
        self._narrative_quality = NarrativeQualityService()

    async def rewrite(
        self,
        script: Script,
        fact_check_report: FactCheckReport,
    ) -> Script:
        failed_claims = [
            claim.to_dict()
            for claim in fact_check_report.claims
            if claim.verdict != "supported"
        ]
        source_payload = [source.to_dict() for source in fact_check_report.sources]
        target_words = max(1, round(script.target_duration_seconds * 2.5))
        minimum_words = max(1, math.ceil(target_words * 0.5))
        maximum_words = max(minimum_words, math.floor(target_words * 1.6))
        prompt = (
            f"Topic: {script.topic}\n"
            f"Target duration: {script.target_duration_seconds} seconds\n"
            f"Target length: approximately {target_words} words\n"
            f"Mandatory length range: {minimum_words}-{maximum_words} words\n\n"
            f"Original narration:\n{script.full_text}\n\n"
            "Claims that must be removed or corrected:\n"
            f"{json.dumps(failed_claims, ensure_ascii=False)}\n\n"
            "Allowed source extracts:\n"
            f"{json.dumps(source_payload, ensure_ascii=False)}\n\n"
            "Rewrite the complete narration now."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        text = ""
        for attempt in range(self._max_generation_attempts):
            text = await self._client.complete(
                model=self._model,
                messages=messages,
                max_tokens=600,
                temperature=0.1,
            )
            word_count = len(text.split())
            candidate = Script.create(
                topic=script.topic,
                full_text=text,
                target_duration_seconds=script.target_duration_seconds,
                provider_used=f"nvidia:{self._model}:fact-grounded-rewrite",
            )
            _, narrative_report = self._narrative_quality.evaluate(candidate)
            length_passed = minimum_words <= word_count <= maximum_words
            if length_passed and narrative_report.passed:
                break
            if attempt < self._max_generation_attempts - 1:
                issue_details = "; ".join(
                    f"{issue.code}: {issue.message}"
                    for issue in narrative_report.issues
                    if issue.blocking
                ) or "none"
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            f"That draft has {word_count} words; required range is "
                            f"{minimum_words}-{maximum_words}. It also failed these deterministic "
                            f"narrative checks: {issue_details}. Rewrite the complete narration "
                            "using only the supplied source extracts. Preserve factual meaning, "
                            "fix every listed check, avoid invitations and repetition, and return "
                            "only narration."
                        ),
                    },
                ]
        return candidate
