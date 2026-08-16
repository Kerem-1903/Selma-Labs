from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.script import Script
from core.domain.value_objects.fact_check_report import FactCheckReport


class ScriptRewriterPort(ABC):
    @abstractmethod
    async def rewrite(
        self,
        script: Script,
        fact_check_report: FactCheckReport,
    ) -> Script:
        raise NotImplementedError
