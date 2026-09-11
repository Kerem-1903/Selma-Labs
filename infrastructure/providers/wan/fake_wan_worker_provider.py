"""Deterministic worker and lifecycle fakes for the pre-GPU gate."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from core.domain.entities.wan_render_job import (
    WanQualityError,
    WanRenderJob,
    WanTechnicalError,
)
from core.domain.ports.wan_compute_lifecycle_port import WanComputeLifecyclePort
from core.domain.ports.wan_worker_provider_port import (
    WanWorkerProviderPort,
    WanWorkerResult,
)
from core.domain.value_objects.media_inspection import MediaInspection


class FakeWanWorkerProvider(WanWorkerProviderPort):
    """Return scripted outcomes per job; unspecified attempts succeed."""

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[str]] | None = None,
        delays: Mapping[str, float] | None = None,
    ) -> None:
        self._outcomes = {key: list(values) for key, values in (outcomes or {}).items()}
        self._delays = dict(delays or {})
        self.calls: dict[str, int] = defaultdict(int)
        self.claims: list[tuple[str, str, str]] = []

    async def render(self, job: WanRenderJob, work_directory: Path) -> WanWorkerResult:
        self.calls[job.job_id] += 1
        call_index = self.calls[job.job_id] - 1
        self.claims.append((job.job_id, job.claimed_by or "", job.profile.name))
        await asyncio.sleep(max(0.0, self._delays.get(job.job_id, 0.0)))
        scripted = self._outcomes.get(job.job_id, [])
        outcome = scripted[call_index] if call_index < len(scripted) else "SUCCESS"
        if (
            outcome in WanTechnicalError._value2member_map_
            and outcome not in {"WRONG_FPS", "WRONG_FRAME_COUNT"}
        ):
            return WanWorkerResult(technical_error=WanTechnicalError(outcome))
        if outcome in WanQualityError._value2member_map_:
            return WanWorkerResult(quality_error=WanQualityError(outcome))

        work_directory.mkdir(parents=True, exist_ok=True)
        output = work_directory / "render.mp4"
        output.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-wan-video")
        fps = job.profile.fps + 1 if outcome == "WRONG_FPS" else job.profile.fps
        frames = job.profile.frame_count + 1 if outcome == "WRONG_FRAME_COUNT" else job.profile.frame_count
        inspection = MediaInspection(
            format_names=("mov", "mp4"),
            duration_seconds=frames / fps,
            width=job.package.width,
            height=job.package.height,
            fps=float(fps),
            fps_rational=f"{fps}/1",
            video_codec="h264",
            pixel_format="yuv420p",
            audio_codec=None,
            audio_sample_rate=None,
            audio_bitrate=None,
            file_size_bytes=output.stat().st_size,
            frame_count=frames,
        )
        return WanWorkerResult(local_output_path=output, inspection=inspection)


class FakeWanComputeLifecycle(WanComputeLifecyclePort):
    def __init__(self, *, provider_auto_stop_enabled: bool = True) -> None:
        self._enabled = provider_auto_stop_enabled
        self.stop_calls = 0

    @property
    def provider_auto_stop_enabled(self) -> bool:
        return self._enabled

    async def stop_own_instance(self) -> None:
        if not self._enabled:
            raise RuntimeError("Provider auto-stop is disabled.")
        self.stop_calls += 1
