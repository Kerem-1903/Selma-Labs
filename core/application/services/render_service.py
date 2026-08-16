"""
RenderService — application-layer orchestration for turning a Timeline plus
narration audio into a persisted RenderedVideo.

Bridges Sprint 6's output (Timeline, where every clip already carries a
downloaded MediaAsset) to Sprint 7's new RenderPort boundary. This is the
"Video Rendering" stage of the roadmap the Sprint 6 README named as its
own future enhancement, built on Timeline without changing its contract.

Depends on RenderPort and StoragePort -- both Ports, never a concrete
provider or storage backend. Unlike TimelineService/SceneAssetMatchingService
(which depend on a concrete application service directly, since their
underlying operations were in-process or already-existing external calls
per ADR-006), RenderService's core operation -- invoking a render engine --
IS a genuinely new external boundary, so it depends on the new RenderPort
Port rather than a concrete class. See RenderPort's own docstring for the
full ADR-006 consistency argument.

Responsibilities, deliberately narrow:
1. Validate the Timeline has something to render and that a narration
   audio path was given.
2. Ask RenderPort to encode -- gets back a RenderResult describing a
   temporary local file, not bytes held in memory (see RenderResult's
   docstring for why).
3. Read that temporary file's bytes exactly once and persist them via
   StoragePort.save(), the same persistence boundary every other binary
   asset in this codebase already goes through (voice audio, downloaded
   video clips).
4. Best-effort clean up the render engine's temporary output file --
   failure to delete a temp file is logged, not raised, since the video
   has already been safely persisted by that point.
5. Assemble and return a RenderedVideo referencing the persisted location.

No re-encoding, no scoring, no quality checks, no fallback rendering
engine. Turning RenderedVideo into a published/distributed asset (upload to
a platform, thumbnail generation, etc.) is out of scope here, same
one-sprint-one-responsibility boundary every prior sprint in this codebase
draws for itself.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from core.domain.entities.rendered_video import RenderedVideo
from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError
from core.domain.ports.render_port import RenderPort
from core.domain.ports.storage_port import StoragePort

logger = logging.getLogger("selma.render_service")

VIDEO_CONTENT_TYPE = "video/mp4"


class RenderService:
    """Renders a Timeline plus narration audio via an injected RenderPort,
    persists the result via an injected StoragePort, and assembles a
    RenderedVideo."""

    def __init__(self, render_port: RenderPort, storage: StoragePort) -> None:
        self._render_port = render_port
        self._storage = storage

    async def render(
        self,
        timeline: Timeline,
        narration_audio_path: str,
        subtitle_path: str | None = None,
    ) -> RenderedVideo:
        """Render ``timeline`` with the narration audio at
        ``narration_audio_path`` and persist the result.

        Args:
            timeline: A Timeline whose clips all have a downloaded asset
                (guaranteed by Sprint 6's TimelineService).
            narration_audio_path: Filesystem path to the narration audio
                file to mux over the assembled video -- not a VoiceTrack,
                see RenderPort's docstring for why.

        Returns:
            A RenderedVideo referencing the persisted video file.

        Raises:
            RenderError: ``timeline`` has no clips, ``narration_audio_path``
                is empty, or the underlying RenderPort implementation
                failed to produce output.
            StorageError: Persisting the rendered video failed.
        """
        if not timeline.clips:
            raise RenderError(
                f"Cannot render Timeline '{timeline.id}': it has no clips."
            )

        narration_audio_path = (narration_audio_path or "").strip()
        if not narration_audio_path:
            raise RenderError(
                "narration_audio_path must not be empty -- RenderService "
                "requires a path to the narration audio file, not a "
                "VoiceTrack (see RenderPort's docstring)."
            )

        logger.info(
            "render_started",
            extra={
                "timeline_id": timeline.id,
                "clip_count": len(timeline.clips),
                "narration_audio_path": narration_audio_path,
            },
        )

        if subtitle_path is None:
            result = await self._render_port.render(timeline, narration_audio_path)
        else:
            result = await self._render_port.render(
                timeline, narration_audio_path, subtitle_path
            )

        try:
            with open(result.output_path, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise RenderError(
                f"RenderPort reported output at '{result.output_path}' but "
                f"it could not be read: {exc}"
            ) from exc

        if not data:
            raise RenderError(
                f"RenderPort produced an empty file at '{result.output_path}' "
                f"for Timeline '{timeline.id}'."
            )

        rendered_video_id = str(uuid.uuid4())
        storage_key = f"render/{rendered_video_id}.mp4"
        reference = await self._storage.save(
            key=storage_key, data=data, content_type=VIDEO_CONTENT_TYPE
        )

        self._cleanup_temp_file(result.output_path)

        rendered_video = RenderedVideo(
            id=rendered_video_id,
            timeline_id=timeline.id,
            video_path=reference.path,
            size_bytes=reference.size_bytes,
            duration_seconds=result.duration_seconds,
            width=result.width,
            height=result.height,
            fps=result.fps,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(
            "render_completed",
            extra={
                "timeline_id": timeline.id,
                "rendered_video_id": rendered_video.id,
                "video_path": rendered_video.video_path,
                "size_bytes": rendered_video.size_bytes,
                "duration_seconds": rendered_video.duration_seconds,
            },
        )

        return rendered_video

    @staticmethod
    def _cleanup_temp_file(path: str) -> None:
        try:
            os.remove(path)
        except OSError as exc:
            # Non-critical: the video is already safely persisted via
            # StoragePort by the time this runs. A leftover temp file is a
            # disk-hygiene concern, not a reason to fail an otherwise
            # successful render.
            logger.warning(
                "render_temp_file_cleanup_failed",
                extra={"path": path, "error": str(exc)},
            )
