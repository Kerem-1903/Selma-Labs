from __future__ import annotations

import json
import re
from typing import cast

from core.domain.exceptions import FactCheckError
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.value_objects.fact_check_report import (
    FactCheckReport,
    FactClaim,
    FactVerdict,
)
from core.domain.value_objects.fact_source import FactSource
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient

VALID_VERDICTS = {"supported", "contradicted", "uncertain"}
QUOTE_STOPWORDS = {
    "a", "an", "the", "bir", "bu", "ve", "ile",
    "da", "de", "ta", "te",
}
TURKISH_SUFFIXES = (
    "larından", "lerinden", "larımızdan", "lerimizden",
    "ından", "inden", "undan", "ünden",
    "ında", "inde", "unda", "ünde",
    "ların", "lerin", "ları", "leri",
    "dan", "den", "tan", "ten",
    "dır", "dir", "dur", "dür", "tır", "tir", "tur", "tür",
    "ı", "i", "u", "ü",
)
NUMBER_WORDS = {
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "sıfır",
    "bir",
    "iki",
    "üç",
    "dört",
    "beş",
    "altı",
    "yedi",
    "sekiz",
    "dokuz",
    "on",
}

SYSTEM_PROMPT = """You are a strict factual verifier for short educational videos.
Use only the supplied source extracts. Identify every externally verifiable factual
claim in the script. Do not use prior knowledge to mark a claim supported.

Return only a JSON object with a 'claims' array. Every claim item must contain:
- claim: one atomic factual assertion in concise form
- verdict: supported, contradicted, or uncertain
- explanation: a short reason grounded in the supplied sources
- source_urls: only URLs from the supplied sources that directly support or contradict it
- evidence_quote: one short verbatim quote from those source extracts

Use 'uncertain' whenever the supplied extracts do not directly establish a claim.
Never omit a factual claim merely because it is false or difficult to verify."""

VERIFICATION_RULES = """Additional mandatory rules:
- Split compound sentences into atomic claims. A claim must not join separate facts
  with 'and', 'while', or a comma.
- Compare quantities and roles independently. If evidence assigns two units to role A
  and one unit to role B, a claim assigning one to A and two to B is contradicted.
- A supported verdict requires the evidence quote to entail the exact subject, action,
  quantity, and role in the claim. Related wording is not enough.
- Copy evidence_quote verbatim from one supplied extract."""

AUDIT_PROMPT = """Audit each claim only against its evidence quote. Ignore the
initial verdict. Return only JSON with an 'audits' array. Each item must contain
index, verdict (supported, contradicted, or uncertain), and explanation.
A claim is supported only when the quote entails the exact subject, action,
quantity, direction, and role. Reversed quantities or roles are contradicted."""


class NvidiaFactCheckProvider(FactCheckPort):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 180.0,
        client: NvidiaChatClient | None = None,
        audit_enabled: bool = True,
        audit_model: str | None = None,
        max_retries: int = 2,
    ) -> None:
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self._model = model
        self._audit_enabled = audit_enabled
        self._audit_model = audit_model or model

    @property
    def provider_identity(self) -> str:
        return f"nvidia:{self._model}"

    async def verify(
        self,
        *,
        topic: str,
        script_text: str,
        sources: list[FactSource],
    ) -> FactCheckReport:
        source_payload = [source.to_dict() for source in sources]
        raw_text = await self._client.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Topic: {topic}\n\nScript:\n{script_text}\n\n"
                        f"{VERIFICATION_RULES}\n\n"
                        "Allowed sources:\n"
                        f"{json.dumps(source_payload, ensure_ascii=False)}"
                    ),
                },
            ],
            max_tokens=900,
            temperature=0.0,
        )
        try:
            data = json.loads(self._extract_json_object(raw_text))
            raw_claims = data.get("claims")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise FactCheckError(f"Invalid NVIDIA fact-check response: {exc}") from exc
        if not isinstance(raw_claims, list) or not raw_claims:
            raise FactCheckError("NVIDIA fact-check response contained no claims.")

        allowed_urls = {source.url for source in sources}
        claims: list[FactClaim] = []
        for raw_claim in raw_claims:
            if not isinstance(raw_claim, dict):
                continue
            claim_text = str(raw_claim.get("claim") or "").strip()
            if not claim_text:
                continue
            verdict = str(raw_claim.get("verdict") or "uncertain").strip().lower()
            if verdict not in VALID_VERDICTS:
                verdict = "uncertain"
            source_urls = [
                str(url)
                for url in (raw_claim.get("source_urls") or [])
                if str(url) in allowed_urls
            ]
            evidence_quote = str(raw_claim.get("evidence_quote") or "").strip()
            quote_is_valid = self._quote_matches_sources(
                evidence_quote,
                source_urls,
                sources,
                claim_text=claim_text,
            )
            if not quote_is_valid:
                evidence_quote = self._find_best_evidence_quote(
                    claim_text,
                    source_urls,
                    sources,
                )
                quote_is_valid = bool(evidence_quote)
            if verdict == "supported" and (not source_urls or not quote_is_valid):
                verdict = "uncertain"
            claims.append(
                FactClaim(
                    claim=claim_text,
                    verdict=cast(FactVerdict, verdict),
                    explanation=str(raw_claim.get("explanation") or "").strip(),
                    source_urls=source_urls,
                    evidence_quote=evidence_quote if quote_is_valid else "",
                )
            )
        if not claims:
            raise FactCheckError("NVIDIA fact-check response had no usable claims.")
        if self._audit_enabled:
            claims = await self._audit_claims(claims)
        return FactCheckReport.create(
            claims=claims,
            sources=sources,
            provider_used=self.provider_identity,
        )

    @staticmethod
    def _extract_json_object(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            candidate = cleaned[start : end + 1]
            return NvidiaFactCheckProvider._repair_json(candidate)
        return cleaned

    @staticmethod
    def _repair_json(text: str) -> str:
        """Best-effort repair of common LLM JSON errors."""
        import json as _json

        # First try as-is
        try:
            _json.loads(text)
            return text
        except _json.JSONDecodeError:
            pass

        repaired = text
        # Remove trailing commas before } or ]
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        # Remove control characters that break JSON strings
        repaired = re.sub(r"[\x00-\x1f](?<![\n\r\t])", " ", repaired)

        try:
            _json.loads(repaired)
            return repaired
        except _json.JSONDecodeError:
            pass

        # Try to close unclosed arrays/objects
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        if open_brackets > 0:
            repaired = repaired.rstrip().rstrip(",") + "]" * open_brackets
        if open_braces > 0:
            repaired = repaired.rstrip().rstrip(",") + "}" * open_braces

        # One more trailing comma cleanup after closing
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        try:
            _json.loads(repaired)
            return repaired
        except _json.JSONDecodeError:
            # Return original; caller will raise a proper FactCheckError
            return text


    @staticmethod
    def _quote_matches_sources(
        evidence_quote: str,
        source_urls: list[str],
        sources: list[FactSource],
        claim_text: str = "",
    ) -> bool:
        quote_tokens = NvidiaFactCheckProvider._evidence_tokens(evidence_quote)
        if not quote_tokens:
            return False
        claim_tokens = NvidiaFactCheckProvider._evidence_tokens(claim_text)
        if claim_tokens:
            claim_coverage = len(claim_tokens & quote_tokens) / len(claim_tokens)
            if claim_coverage < 0.8:
                return False
        quote_numbers = quote_tokens & NUMBER_WORDS
        for source in sources:
            if source.url not in source_urls:
                continue
            for sentence in re.split(r"[.!?;]+", source.extract):
                sentence_tokens = NvidiaFactCheckProvider._evidence_tokens(sentence)
                if not sentence_tokens:
                    continue
                if quote_numbers and not quote_numbers.issubset(sentence_tokens):
                    continue
                overlap = len(quote_tokens & sentence_tokens) / len(quote_tokens)
                if overlap >= 0.8:
                    return True
        return False

    @staticmethod
    def _evidence_tokens(text: str) -> set[str]:
        return {
            NvidiaFactCheckProvider._normalize_evidence_token(token)
            for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
            if token not in QUOTE_STOPWORDS
        }

    @staticmethod
    def _normalize_evidence_token(token: str) -> str:
        """Reduce common Turkish case/possessive endings for quote matching."""
        for suffix in TURKISH_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                return token[: -len(suffix)]
        return token

    @staticmethod
    def _find_best_evidence_quote(
        claim_text: str,
        source_urls: list[str],
        sources: list[FactSource],
    ) -> str:
        claim_tokens = NvidiaFactCheckProvider._evidence_tokens(claim_text)
        claim_numbers = claim_tokens & NUMBER_WORDS
        if not claim_tokens:
            return ""
        best_sentence = ""
        best_overlap = 0.0
        for source in sources:
            if source.url not in source_urls:
                continue
            for sentence in re.split(r"(?<=[.!?;])\s+", source.extract):
                sentence_tokens = NvidiaFactCheckProvider._evidence_tokens(sentence)
                if claim_numbers and not claim_numbers.issubset(sentence_tokens):
                    continue
                overlap = len(claim_tokens & sentence_tokens) / len(claim_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_sentence = sentence.strip()
        return best_sentence if best_overlap >= 0.6 else ""

    async def _audit_claims(self, claims: list[FactClaim]) -> list[FactClaim]:
        audit_input = [
            {
                "index": index,
                "claim": claim.claim,
                "initial_verdict": claim.verdict,
                "evidence_quote": claim.evidence_quote,
            }
            for index, claim in enumerate(claims)
        ]
        raw_text = await self._client.complete(
            model=self._audit_model,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(audit_input, ensure_ascii=False),
                },
            ],
            max_tokens=600,
            temperature=0.0,
        )
        try:
            data = json.loads(self._extract_json_object(raw_text))
            raw_audits = data.get("audits")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise FactCheckError(f"Invalid NVIDIA fact-check audit response: {exc}") from exc
        if not isinstance(raw_audits, list):
            raise FactCheckError("NVIDIA fact-check audit response contained no audits.")

        audits: dict[int, tuple[str, str]] = {}
        for raw_audit in raw_audits:
            if not isinstance(raw_audit, dict):
                continue
            try:
                index = int(raw_audit.get("index"))
            except (TypeError, ValueError):
                continue
            verdict = str(raw_audit.get("verdict") or "uncertain").strip().lower()
            if verdict not in VALID_VERDICTS:
                verdict = "uncertain"
            audits[index] = (
                verdict,
                str(raw_audit.get("explanation") or "").strip(),
            )

        audited_claims: list[FactClaim] = []
        for index, claim in enumerate(claims):
            audit_verdict, audit_explanation = audits.get(
                index,
                ("uncertain", "The second-pass audit did not return this claim."),
            )
            if claim.verdict == "contradicted" or audit_verdict == "contradicted":
                final_verdict = "contradicted"
            elif claim.verdict == "supported" and audit_verdict == "supported":
                final_verdict = "supported"
            else:
                final_verdict = "uncertain"
            audited_claims.append(
                FactClaim(
                    claim=claim.claim,
                    verdict=cast(FactVerdict, final_verdict),
                    explanation=audit_explanation or claim.explanation,
                    source_urls=claim.source_urls,
                    evidence_quote=claim.evidence_quote,
                )
            )
        return audited_claims
