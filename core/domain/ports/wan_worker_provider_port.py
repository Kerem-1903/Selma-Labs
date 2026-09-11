from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from core.domain.entities.wan_render_job import (
    WanQualityError,
    WanRenderJob,
    WanTechnicalError,
)
from core.domain.value_objects.media_inspection import MediaInspection


@dataclass(frozen=True)
class WanWorkerResult:
    local_output_path: Path | None = None
    inspection: MediaInspection | None = None
    technical_error: WanTechnicalError | None = None
    quality_error: WanQualityError | None = None


class WanWorkerProviderPort(ABC):
    @abstractmethod
    async def render(self, job: WanRenderJob, work_directory: Path) -> WanWorkerResult:
        raise NotImplementedError

