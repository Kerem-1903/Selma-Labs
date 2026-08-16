from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.domain.value_objects.fact_source import FactSource

FactVerdict = Literal["supported", "contradicted", "uncertain"]


@dataclass(frozen=True)
class FactClaim:
    claim: str
    verdict: FactVerdict
    explanation: str
    source_urls: list[str]
    evidence_quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "verdict": self.verdict,
            "explanation": self.explanation,
            "source_urls": list(self.source_urls),
            "evidence_quote": self.evidence_quote,
        }


@dataclass(frozen=True)
class FactCheckReport:
    verified: bool
    claims: list[FactClaim]
    sources: list[FactSource]
    provider_used: str

    @staticmethod
    def create(
        *,
        claims: list[FactClaim],
        sources: list[FactSource],
        provider_used: str,
    ) -> "FactCheckReport":
        verified = bool(claims) and all(
            claim.verdict == "supported"
            and bool(claim.source_urls)
            and bool(claim.evidence_quote)
            for claim in claims
        )
        return FactCheckReport(
            verified=verified,
            claims=list(claims),
            sources=list(sources),
            provider_used=provider_used,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "provider_used": self.provider_used,
            "claims": [claim.to_dict() for claim in self.claims],
            "sources": [source.to_dict() for source in self.sources],
        }
