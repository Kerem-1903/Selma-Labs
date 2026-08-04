"""
RenderedVideo entity.

The persisted, final result of rendering one Timeline into an actual video
file -- the last entity in the pipeline (Script -> VoiceTrack -> ScenePlan
-> AssetMatchPlan -> Timeline -> RenderedVideo). Plain dataclass, no
framework dependency, same pattern as every prior entity in this codebase.

References only ``timeline_id`` (its one direct parent), same ancestry
convention Timeline/AssetMatchPlan/ScenePlan already established -- a
consumer that needs the full chain follows RenderedVideo -> Timeline ->
AssetMatchPlan -> ScenePlan -> Script/VoiceTrack rather than this entity
duplicating ancestor ids it doesn't itself depend on.

**Deliberately has no ``provider_used`` field**, unlike Script
(``provider_used``), VoiceTrack (``provider``), and ScenePlan
(``provider_used``). This is a real deviation from an established pattern
in this codebase, not an oversight, and it deserves the same scrutiny given
to any deviation:

Script/VoiceTrack/ScenePlan record which provider generated them because
the provider is a genuinely *content-shaping* choice for those entities --
a different script-generation model produces materially different wording,
a different voice model produces a different voice, a different scene
planner might choose different keywords or moods. A downstream consumer
(or a human debugging a bad result) may legitimately need to know which
provider is responsible for that content. MediaAsset.provider follows the
same logic for a different reason: it carries real domain/legal weight
(attribution, license) tied to *which catalog the asset came from*.

RenderedVideo is not like either case. RenderPort's whole contract is that
``render(timeline, narration_audio_path)`` produces the *same* video --
same clips, same order, same audio -- regardless of which engine
implements it; the engine is an interchangeable execution detail, exactly
what Ports & Adapters exists to hide. Nothing in this domain currently
reads or branches on which render engine produced a RenderedVideo, and
there is no attribution/license obligation analogous to MediaAsset's tied
to "FFmpeg" vs. a future cloud renderer. Recording it here would be
provenance for provenance's sake, not domain data the business logic
depends on -- the same "no unjustified field" standard already applied to
reject `Timeline.metadata`/`TimelineClip.metadata` speculative content in
the Sprint 6 review.

If a genuine domain need for this appears later (e.g. licensing terms that
differ per render engine, or a UI that needs to disclose which renderer
produced a given file), adding a field to a frozen dataclass at that point
is a small, additive, low-risk change -- there is no real cost being
avoided by omitting it now. Until then, `RenderService` logs the render
provider identity as structured logging (same as every other service in
this codebase already logs provider identity for its own operations
without also persisting it onto the entity), which is enough for debugging
and operational visibility without committing the domain model to it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class RenderedVideo:
    id: str
    timeline_id: Optional[str]
    video_path: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    created_at: datetime

    @staticmethod
    def create(
        *,
        timeline_id: Optional[str],
        video_path: str,
        size_bytes: int,
        duration_seconds: float,
        width: int,
        height: int,
        fps: float,
    ) -> "RenderedVideo":
        return RenderedVideo(
            id=str(uuid.uuid4()),
            timeline_id=timeline_id,
            video_path=video_path,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            fps=fps,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict:
        """Export a plain-dict shape for CLI/JSON output. Mirrors
        Timeline.to_dict()/AssetMatchPlan.to_dict()."""
        return {
            "id": self.id,
            "timeline_id": self.timeline_id,
            "video_path": self.video_path,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "created_at": self.created_at.isoformat(),
        }
