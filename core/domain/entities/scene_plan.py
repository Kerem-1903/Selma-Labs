"""
ScenePlan entity.

The persisted-shape result of scene planning for one Script/VoiceTrack
pair — what a later sprint's VideoSearchService/Asset Matching step will
actually consume. Plain dataclass, no framework dependency, same pattern as
Script and VoiceTrack.

Not literally persisted to storage in this sprint (no StoragePort involved
— a ScenePlan is data, not a binary asset), but structured exactly like
something that will be handed off wholesale to the next sprint's service,
the same way VoiceTrack is handed to a future Scene Assembly step.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from core.domain.value_objects.scene import Scene


@dataclass(frozen=True)
class ScenePlan:
    id: str
    script_id: Optional[str]
    voice_track_id: Optional[str]
    total_duration_seconds: float
    provider_used: str
    scenes: list[Scene]
    created_at: datetime

    @staticmethod
    def create(
        *,
        script_id: Optional[str],
        voice_track_id: Optional[str],
        total_duration_seconds: float,
        provider_used: str,
        scenes: list[Scene],
    ) -> "ScenePlan":
        return ScenePlan(
            id=str(uuid.uuid4()),
            script_id=script_id,
            voice_track_id=voice_track_id,
            total_duration_seconds=total_duration_seconds,
            provider_used=provider_used,
            scenes=scenes,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict:
        """Export a plain-dict shape for CLI/JSON output or a future
        downstream consumer (e.g. VideoSearchService's Asset Matching
        step). Mirrors VoiceTrack.to_dict()/MediaAsset.to_dict()."""
        return {
            "id": self.id,
            "script_id": self.script_id,
            "voice_track_id": self.voice_track_id,
            "total_duration_seconds": self.total_duration_seconds,
            "provider_used": self.provider_used,
            "created_at": self.created_at.isoformat(),
            "scenes": [
                {
                    "index": scene.index,
                    "start_time": scene.start_time,
                    "end_time": scene.end_time,
                    "narration": scene.narration,
                    "search_keywords": scene.search_keywords,
                    "generation_prompt": scene.generation_prompt,
                    "detected_objects": scene.detected_objects,
                    "location": scene.location,
                    "mood": scene.mood,
                    "visual_priority": scene.visual_priority,
                    "visual_job": scene.visual_job,
                    "required_subjects": list(scene.required_subjects),
                    "required_actions": list(scene.required_actions),
                    "required_relations": list(scene.required_relations),
                    "forbidden_dominant_subjects": list(scene.forbidden_dominant_subjects),
                    "explanation_mode": scene.explanation_mode,
                    "overlay_labels": list(scene.overlay_labels),
                    "explanatory_required": scene.explanatory_required,
                }
                for scene in self.scenes
            ],
        }
