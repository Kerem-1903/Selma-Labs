from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.domain.entities.wan_render_job import WanRenderJob, WanTechnicalError
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.value_objects.media_inspection import MediaInspection


@dataclass(frozen=True)
class WanOutputVerification:
    accepted: bool
    error: WanTechnicalError | None = None
    inspection: MediaInspection | None = None


class WanOutputVerificationService:
    def __init__(self, inspector: MediaInspectionPort) -> None:
        self._inspector = inspector

    async def verify(
        self,
        job: WanRenderJob,
        output_path: str | Path,
        *,
        inspection: MediaInspection | None = None,
    ) -> WanOutputVerification:
        path = Path(output_path)
        if not path.is_file() or path.stat().st_size <= 0:
            return WanOutputVerification(False, WanTechnicalError.BROKEN_MP4)
        try:
            media = inspection or await self._inspector.inspect(str(path))
        except Exception:  # noqa: BLE001 - provider failures are normalized at this boundary
            return WanOutputVerification(False, WanTechnicalError.FFPROBE_FAILED)
        if not ({"mp4", "mov"} & set(media.format_names)) or not media.video_codec:
            return WanOutputVerification(False, WanTechnicalError.BROKEN_MP4, media)
        if abs(media.fps - job.profile.fps) > 0.01:
            return WanOutputVerification(False, WanTechnicalError.WRONG_FPS, media)
        if media.frame_count != job.profile.frame_count:
            return WanOutputVerification(False, WanTechnicalError.WRONG_FRAME_COUNT, media)
        return WanOutputVerification(True, inspection=media)
