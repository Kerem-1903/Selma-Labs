from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.fact_check_report import FactCheckReport
from core.domain.value_objects.fact_source import FactSource


class FactCheckPort(ABC):
    @property
    @abstractmethod
    def provider_identity(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def verify(
        self,
        *,
        topic: str,
        script_text: str,
        sources: list[FactSource],
    ) -> FactCheckReport:
        raise NotImplementedError
