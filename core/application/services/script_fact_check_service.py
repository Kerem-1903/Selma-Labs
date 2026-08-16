from __future__ import annotations

from core.domain.entities.script import Script
from core.domain.exceptions import FactCheckError
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.ports.fact_source_port import FactSourcePort
from core.domain.ports.script_rewriter_port import ScriptRewriterPort
from core.domain.value_objects.fact_check_report import FactCheckReport
from core.application.services.script_service import ScriptService


class ScriptFactCheckService:
    """Grounds script claims in retrieved sources before paid media work."""

    def __init__(
        self,
        source_provider: FactSourcePort,
        fact_check_provider: FactCheckPort,
        max_sources: int = 5,
    ) -> None:
        self._source_provider = source_provider
        self._fact_check_provider = fact_check_provider
        self._max_sources = max_sources

    async def verify(self, script: Script) -> FactCheckReport:
        sources = await self._source_provider.search(
            script.topic,
            max_results=self._max_sources,
        )
        if not sources:
            raise FactCheckError(
                f"No reliable fact-check sources found for topic: {script.topic!r}."
            )
        return await self._fact_check_provider.verify(
            topic=script.topic,
            script_text=script.full_text,
            sources=sources,
        )

    async def verify_with_rewrites(
        self,
        script: Script,
        rewriter: ScriptRewriterPort,
        max_rewrites: int = 1,
    ) -> tuple[Script, list[FactCheckReport]]:
        current_script = script
        reports: list[FactCheckReport] = []
        rewrite_limit = max(0, max_rewrites)
        for attempt in range(rewrite_limit + 1):
            report = await self.verify(current_script)
            reports.append(report)
            if report.verified or attempt == rewrite_limit:
                return current_script, reports
            current_script = await rewriter.rewrite(current_script, report)
            ScriptService.validate_output(
                current_script,
                current_script.target_duration_seconds,
            )
        return current_script, reports
