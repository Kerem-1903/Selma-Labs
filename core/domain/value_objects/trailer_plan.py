"""Traceable trailer shot and plan contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.trailer_timeline import TrailerTimeline


@dataclass(frozen=True)
class TrailerShot:
    shot_id: str
    beat_id: str
    source_scene_id: str
    purpose: str
    start_frame: int
    end_frame: int
    character_id: str
    pose_id: str
    location_id: str
    dialogue: str = ""
    system_voice: str = ""
    music_cue: str = ""
    sfx_cue: str = ""
    spoiler_level: str = "SAFE"
    production_method: str = "STORYBOARD"
    source_shot_id: str = ""

    def __post_init__(self) -> None:
        required = ((self.shot_id, "shot_id"), (self.beat_id, "beat_id"), (self.source_scene_id, "source_scene_id"), (self.purpose, "purpose"), (self.character_id, "character_id"), (self.pose_id, "pose_id"), (self.location_id, "location_id"))
        if any(not str(value).strip() for value, _ in required):
            raise PreProductionValidationError("Trailer shot identity and purpose are required.")
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise PreProductionValidationError("Trailer shot frame range is invalid.")
        if self.spoiler_level not in {"SAFE", "ALLOWED_REVEAL", "HIDDEN"}:
            raise PreProductionValidationError("Unknown trailer spoiler level.")
        if self.spoiler_level == "HIDDEN":
            raise PreProductionValidationError("Hidden spoiler material cannot be emitted as a trailer shot.")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "beat_id": self.beat_id,
            "source_scene_id": self.source_scene_id,
            "source_shot_id": self.source_shot_id,
            "purpose": self.purpose,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
            "character_id": self.character_id,
            "pose_id": self.pose_id,
            "location_id": self.location_id,
            "dialogue": self.dialogue,
            "system_voice": self.system_voice,
            "music_cue": self.music_cue,
            "sfx_cue": self.sfx_cue,
            "spoiler_level": self.spoiler_level,
            "production_method": self.production_method,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrailerShot":
        return cls(
            shot_id=str(data.get("shot_id", "")),
            beat_id=str(data.get("beat_id", "")),
            source_scene_id=str(data.get("source_scene_id", "")),
            source_shot_id=str(data.get("source_shot_id", "")),
            purpose=str(data.get("purpose", "")),
            start_frame=int(data.get("start_frame", -1)),
            end_frame=int(data.get("end_frame", 0)),
            character_id=str(data.get("character_id", "")),
            pose_id=str(data.get("pose_id", "")),
            location_id=str(data.get("location_id", "")),
            dialogue=str(data.get("dialogue", "")),
            system_voice=str(data.get("system_voice", "")),
            music_cue=str(data.get("music_cue", "")),
            sfx_cue=str(data.get("sfx_cue", "")),
            spoiler_level=str(data.get("spoiler_level", "SAFE")),
            production_method=str(data.get("production_method", "STORYBOARD")),
        )


@dataclass(frozen=True)
class TrailerPlan:
    schema_version: int
    brief: Mapping[str, Any]
    timeline: TrailerTimeline
    shots: tuple[TrailerShot, ...]
    source_episode_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.source_episode_id.strip():
            raise PreProductionValidationError("Trailer plan identity is incomplete.")
        if not self.shots:
            raise PreProductionValidationError("Trailer plan requires shots.")
        expected = self.timeline.beats[0].start_frame
        for shot in self.shots:
            if shot.start_frame != expected:
                raise PreProductionValidationError("Trailer shots must be contiguous and ordered.")
            expected = shot.end_frame
        if expected != self.timeline.duration_frames:
            raise PreProductionValidationError("Trailer shots must cover exactly the trailer duration.")
        valid_beats = {beat.beat_id for beat in self.timeline.beats}
        if any(shot.beat_id not in valid_beats for shot in self.shots):
            raise PreProductionValidationError("Trailer shot references an unknown beat.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_episode_id": self.source_episode_id,
            "brief": dict(self.brief),
            "timeline": self.timeline.to_dict(),
            "shots": [shot.to_dict() for shot in self.shots],
            "shot_count": len(self.shots),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrailerPlan":
        raw_timeline = data.get("timeline", {})
        if not isinstance(raw_timeline, Mapping):
            raise TypeError("Trailer plan timeline must be an object.")
        raw_brief = data.get("brief", {})
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            source_episode_id=str(data.get("source_episode_id", "")),
            brief=dict(raw_brief) if isinstance(raw_brief, Mapping) else {},
            timeline=TrailerTimeline.from_dict(raw_timeline),
            shots=tuple(TrailerShot.from_dict(item) for item in data.get("shots", ()) if isinstance(item, Mapping)),
            warnings=tuple(str(item) for item in data.get("warnings", ())),
        )
