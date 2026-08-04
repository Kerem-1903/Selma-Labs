"""
RenderPort — the contract every video-rendering engine must satisfy.

Unlike Sprint 6's TimelineService (which reused VideoSourcePort/StoragePort
and introduced no new Port, per ADR-006), Sprint 7 does introduce one new
Port here. This is deliberate, not an inconsistency with ADR-006: ADR-006's
rule is "no new Port for in-process decisions over data already inside the
application, only for genuinely new external systems." Encoding a Timeline
into a video file is not an in-process decision -- it requires invoking an
actual external process (FFmpeg today, potentially a cloud rendering API or
Remotion/MoviePy later), the same category of genuine boundary that
justified VideoSourcePort/VoiceGeneratorPort/ScriptGeneratorPort/
ScenePlanningPort in earlier sprints. RenderPort is that boundary for
rendering.

Only ``render()`` is required. Deliberately does NOT accept a VoiceTrack --
only the two things rendering actually needs: the Timeline (clips, in
order, each with a downloaded MediaAsset) and the narration audio file's
path. A render engine has no legitimate use for VoiceTrack's other fields
(``audio_id``, ``script_id``, ``provider``, ``sample_rate``, ``segments``)
-- coupling this Port to that entity would make RenderPort depend on
voice-generation's domain shape for a value it never reads beyond
``file_path``. This mirrors how VideoSourcePort.download() takes a
MediaAsset (what it actually needs) rather than a whole SceneAssetMatch.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.timeline import Timeline
from core.domain.value_objects.render_result import RenderResult


class RenderPort(ABC):
    """Encodes a Timeline plus narration audio into a finished video file."""

    @abstractmethod
    async def render(self, timeline: Timeline, narration_audio_path: str) -> RenderResult:
        """Render ``timeline``'s clips, in order, muxed with the narration
        audio at ``narration_audio_path``, into one video file.

        Args:
            timeline: The fully-resolved Timeline to render. Every clip's
                ``asset.local_path`` must already be set (Sprint 6's
                TimelineService guarantees this).
            narration_audio_path: Filesystem path to the narration audio
                file to mux over the assembled video. Not a VoiceTrack --
                see module docstring for why.

        Returns:
            A RenderResult describing the engine's output on local disk.
            The caller (RenderService) is responsible for persisting it via
            StoragePort and for any temp-file cleanup.

        Raises:
            RenderError: ``timeline`` has no clips, ``narration_audio_path``
                could not be read, or the underlying engine failed to
                produce output.
        """
        raise NotImplementedError
