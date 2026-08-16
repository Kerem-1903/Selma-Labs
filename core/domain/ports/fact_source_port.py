from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.fact_source import FactSource


class FactSourcePort(ABC):
    @property
    @abstractmethod
    def provider_identity(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def search(self, topic: str, max_results: int) -> list[FactSource]:
        raise NotImplementedError
