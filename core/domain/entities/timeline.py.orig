"""
Timeline entity.

The result of selecting and downloading one final MediaAsset per scene from
an AssetMatchPlan — what a later sprint's rendering step (ffmpeg/moviepy/
Remotion, Sprint 7+) will consume to actually cut the final video. Plain
dataclass, no framework dependency, same pattern as Script/VoiceTrack/
ScenePlan/AssetMatchPlan.

Not persisted to storage in this sprint (no StoragePort involved for the
Timeline structure itself — it is data, not a binary asset, same reasoning
ScenePlan and AssetMatchPlan already document), but structured exactly like
something that will be handed off wholesale to Sprint 7's rendering service.

References only ``asset_match_plan_id`` (its one direct parent), not also
``scene_plan_id``/``script_id``/``voice_track_id`` — same ancestry
convention AssetMatchPlan already established: a consumer that needs the
full chain follows Timeline -> AssetMatchPlan -> ScenePlan -> Script/
VoiceTrack rather than this entity duplicating ancestor ids it doesn't
itself depend on.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.domain.value_objects.timeline_clip import TimelineClip


@dataclass(frozen=True)
class Timeline:
    id: str
    asset_match_plan_id: Optional[str]
    clips: list[TimelineClip]
    total_duration_seconds: float
    created_at: datetime
    # Extension point only (Sprint 6) — same reasoning as
    # TimelineClip.metadata (see that module's docstring). Reserved for
    # future render-wide settings a rendering sprint will need (e.g. fps,
    # resolution, aspect ratio, background music reference, render
    # profile). Empty by default; no service in this sprint reads, writes,
    # or validates it.
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def create(
        *,
        asset_match_plan_id: Optional[str],
        clips: list[TimelineClip],
    ) -> "Timeline":
        total_duration_seconds = (
            max(clip.scene.end_time for clip in clips) if clips else 0.0
        )
        return Timeline(
            id=str(uuid.uuid4()),
            asset_match_plan_id=asset_match_plan_id,
            clips=clips,
            total_duration_seconds=total_duration_seconds,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict:
        """Export a plain-dict shape for CLI/JSON output or a future
        downstream consumer (e.g. Sprint 7's rendering service). Mirrors
        AssetMatchPlan.to_dict()/ScenePlan.to_dict()."""
        return {
            "id": self.id,
            "asset_match_plan_id": self.asset_match_plan_id,
            "total_duration_seconds": self.total_duration_seconds,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "clips": [
                {
                    "scene_index": clip.scene.index,
                    "start_time": clip.scene.start_time,
                    "end_time": clip.scene.end_time,
                    "narration": clip.scene.narration,
                    "asset": clip.asset.to_dict(),
                    "metadata": clip.metadata,
                }
                for clip in self.clips
            ],
        }
