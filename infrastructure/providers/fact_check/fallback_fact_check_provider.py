"""Availability fallback without weakening fact-check policy."""
from __future__ import annotations

from core.domain.exceptions import FactCheckError, ProviderError
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.value_objects.fact_check_report import FactCheckReport
from core.domain.value_objects.fact_source import FactSource


class FallbackFactCheckProvider(FactCheckPort):
    def __init__(self, primary: FactCheckPort, fallback: FactCheckPort) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def provider_identity(self) -> str:
        return f"fallback:{self._primary.provider_identity}->{self._fallback.provider_identity}"

    async def verify(
        self,
        *,
        topic: str,
        script_text: str,
        sources: list[FactSource],
    ) -> FactCheckReport:
        try:
            return await self._primary.verify(
                topic=topic,
                script_text=script_text,
                sources=sources,
            )
        except (ProviderError, FactCheckError):
            return await self._fallback.verify(
                topic=topic,
                script_text=script_text,
                sources=sources,
            )
