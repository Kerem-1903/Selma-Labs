"""
AssetMatchPlan entity.

The result of matching visual asset candidates to every Scene in one
ScenePlan — what a later sprint's Video Assembly step will consume to pick
one asset per scene and render the final video. Plain dataclass, no
framework dependency, same pattern as Script/VoiceTrack/ScenePlan.

Not persisted to storage in this sprint (no StoragePort involved — like
ScenePlan, this is data, not a binary asset), but structured exactly like
something that will be handed off wholesale to the next sprint's service,
same reasoning ScenePlan documented for its own relationship to Video
Assembly.

References only ``scene_plan_id`` (its one direct parent), not
``script_id``/``voice_track_id`` — those are ScenePlan's concern, not this
entity's; a consumer that needs the full chain can follow
AssetMatchPlan -> ScenePlan -> Script/VoiceTrack rather than this entity
duplicating ancestor ids it doesn't itself depend on.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from core.domain.value_objects.scene_asset_match import SceneAssetMatch


@dataclass(frozen=True)
class AssetMatchPlan:
    id: str
    scene_plan_id: Optional[str]
    matches: list[SceneAssetMatch]
    created_at: datetime

    @staticmethod
    def create(
        *,
        scene_plan_id: Optional[str],
        matches: list[SceneAssetMatch],
    ) -> "AssetMatchPlan":
        return AssetMatchPlan(
            id=str(uuid.uuid4()),
            scene_plan_id=scene_plan_id,
            matches=matches,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict:
        """Export a plain-dict shape for CLI/JSON output or a future
        downstream consumer (e.g. Video Assembly's asset selection step).
        Mirrors ScenePlan.to_dict()/MediaAsset.to_dict()."""
        return {
            "id": self.id,
            "scene_plan_id": self.scene_plan_id,
            "created_at": self.created_at.isoformat(),
            "matches": [
                {
                    "scene_index": match.scene.index,
                    "scene_narration": match.scene.narration,
                    "search_keywords": match.scene.search_keywords,
                    "asset_count": len(match.assets),
                    "assets": [asset.to_dict() for asset in match.assets],
                }
                for match in self.matches
            ],
        }
