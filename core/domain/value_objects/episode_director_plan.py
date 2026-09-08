"""Provider-neutral episode director plan and timeline contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.domain.exceptions import PreProductionValidationError

POSE_IDS = (
    "FRONT_NEUTRAL",
    "THREE_QUARTER_LEFT",
    "PROFILE_LEFT",
    "THREE_QUARTER_RIGHT",
    "BACK_FULL_BODY",
)

_BEATS = frozenset({"setup", "context", "conflict", "reveal", "reaction", "transition", "payoff"})
_SHOT_SIZES = frozenset({"wide", "medium", "close_up", "profile", "insert"})
_TRACKS = ("SCRIPT", "CHARACTER", "BACKGROUND", "CAMERA", "DIALOGUE", "EFFECTS")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _id(value: object, field_name: str) -> str:
    result = _text(value, field_name)
    if not _SAFE_ID.fullmatch(result):
        raise PreProductionValidationError(f"{field_name} must be storage-safe.")
    return result


def _key(value: object, field_name: str) -> str:
    result = _text(value, field_name).replace("\\", "/")
    if result.startswith("/") or ":" in result or ".." in result.split("/"):
        raise PreProductionValidationError(f"{field_name} must be a portable relative storage key.")
    return result


@dataclass(frozen=True)
class DirectorCharacterRequirement:
    character_id: str
    pose_ids: tuple[str, ...]
    status: str = "PLANNED"
    pose_pack_manifest_ref: str = ""
    pose_asset_refs: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_id", _id(self.character_id, "character_id"))
        if not self.pose_ids or any(pose not in POSE_IDS for pose in self.pose_ids):
            raise PreProductionValidationError("Character pose requirements contain an unknown pose.")
        if self.status not in {"MISSING", "PLANNED", "READY"}:
            raise PreProductionValidationError("Unknown character pose requirement status.")
        if self.pose_pack_manifest_ref:
            object.__setattr__(self, "pose_pack_manifest_ref", _key(self.pose_pack_manifest_ref, "pose_pack_manifest_ref"))
        if any(pose not in self.pose_ids or not str(asset).strip() for pose, asset in self.pose_asset_refs.items()):
            raise PreProductionValidationError("Character pose asset references are invalid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "pose_ids": list(self.pose_ids),
            "status": self.status,
            "pose_pack_manifest_ref": self.pose_pack_manifest_ref,
            "pose_asset_refs": dict(self.pose_asset_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DirectorCharacterRequirement":
        raw_refs = data.get("pose_asset_refs", {})
        return cls(
            character_id=str(data.get("character_id", "")),
            pose_ids=tuple(str(value) for value in data.get("pose_ids", ())),
            status=str(data.get("status", "PLANNED")),
            pose_pack_manifest_ref=str(data.get("pose_pack_manifest_ref", "")),
            pose_asset_refs={str(key): str(value) for key, value in raw_refs.items()} if isinstance(raw_refs, Mapping) else {},
        )


@dataclass(frozen=True)
class DirectorBackgroundRequirement:
    recipe_id: str
    location_id: str
    shot_scale: str
    camera_angle: str
    weather: str
    time_of_day: str
    prompt: str
    scene_ids: tuple[str, ...] = ()
    shot_ids: tuple[str, ...] = ()
    status: str = "PLANNED"
    asset_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _id(self.recipe_id, "recipe_id"))
        object.__setattr__(self, "location_id", _id(self.location_id, "location_id"))
        if self.status not in {"MISSING", "PLANNED", "READY"}:
            raise PreProductionValidationError("Unknown background requirement status.")
        if not self.prompt.strip() or not self.shot_scale.strip() or not self.camera_angle.strip():
            raise PreProductionValidationError("Background requirement is incomplete.")
        if self.asset_ref:
            object.__setattr__(self, "asset_ref", _key(self.asset_ref, "asset_ref"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "location_id": self.location_id,
            "shot_scale": self.shot_scale,
            "camera_angle": self.camera_angle,
            "weather": self.weather,
            "time_of_day": self.time_of_day,
            "prompt": self.prompt,
            "scene_ids": list(self.scene_ids),
            "shot_ids": list(self.shot_ids),
            "status": self.status,
            "asset_ref": self.asset_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DirectorBackgroundRequirement":
        return cls(
            recipe_id=str(data.get("recipe_id", "")),
            location_id=str(data.get("location_id", "")),
            shot_scale=str(data.get("shot_scale", "")),
            camera_angle=str(data.get("camera_angle", "")),
            weather=str(data.get("weather", "clear")),
            time_of_day=str(data.get("time_of_day", "day")),
            prompt=str(data.get("prompt", "")),
            scene_ids=tuple(str(value) for value in data.get("scene_ids", ())),
            shot_ids=tuple(str(value) for value in data.get("shot_ids", ())),
            status=str(data.get("status", "PLANNED")),
            asset_ref=str(data.get("asset_ref", "")),
        )


@dataclass(frozen=True)
class DirectorShot:
    shot_id: str
    scene_id: str
    purpose: str
    story_beat: str
    source_script_lines: tuple[str, ...]
    dialogue: str
    duration_seconds: float
    character_id: str
    character_pose_id: str
    pose_reason: str
    character_action: str
    expression: str
    shot_size: str
    camera_angle: str
    camera_movement: str
    background_recipe_id: str
    background_prompt: str
    foreground_effects: tuple[str, ...]
    transition_in: str
    transition_out: str
    start_ms: int
    end_ms: int
    reasoning: str
    character_pose_asset_ref: str = ""
    background_asset_ref: str = ""

    def __post_init__(self) -> None:
        for value, name in ((self.shot_id, "shot_id"), (self.scene_id, "scene_id"), (self.character_id, "character_id")):
            _id(value, name)
        if self.character_pose_id not in POSE_IDS:
            raise PreProductionValidationError(f"Unknown character pose: {self.character_pose_id}")
        if self.story_beat not in _BEATS or self.shot_size not in _SHOT_SIZES:
            raise PreProductionValidationError("Director shot contains an unsupported beat or shot size.")
        if self.duration_seconds <= 0 or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise PreProductionValidationError("Director shot timing is invalid.")
        if self.end_ms - self.start_ms != round(self.duration_seconds * 1000):
            raise PreProductionValidationError("Director shot milliseconds and duration disagree.")
        if self.character_pose_asset_ref:
            object.__setattr__(self, "character_pose_asset_ref", _key(self.character_pose_asset_ref, "character_pose_asset_ref"))
        if self.background_asset_ref:
            object.__setattr__(self, "background_asset_ref", _key(self.background_asset_ref, "background_asset_ref"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "scene_id": self.scene_id,
            "purpose": self.purpose,
            "story_beat": self.story_beat,
            "source_script_lines": list(self.source_script_lines),
            "dialogue": self.dialogue,
            "duration_seconds": self.duration_seconds,
            "character_id": self.character_id,
            "character_pose_id": self.character_pose_id,
            "pose_reason": self.pose_reason,
            "character_action": self.character_action,
            "expression": self.expression,
            "shot_size": self.shot_size,
            "camera_angle": self.camera_angle,
            "camera_movement": self.camera_movement,
            "background_recipe_id": self.background_recipe_id,
            "background_prompt": self.background_prompt,
            "foreground_effects": list(self.foreground_effects),
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "reasoning": self.reasoning,
            "character_pose_asset_ref": self.character_pose_asset_ref,
            "background_asset_ref": self.background_asset_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DirectorShot":
        return cls(
            shot_id=str(data.get("shot_id", "")),
            scene_id=str(data.get("scene_id", "")),
            purpose=str(data.get("purpose", "")),
            story_beat=str(data.get("story_beat", "")),
            source_script_lines=tuple(str(value) for value in data.get("source_script_lines", ())),
            dialogue=str(data.get("dialogue", "")),
            duration_seconds=float(data.get("duration_seconds", 0)),
            character_id=str(data.get("character_id", "")),
            character_pose_id=str(data.get("character_pose_id", "")),
            pose_reason=str(data.get("pose_reason", "")),
            character_action=str(data.get("character_action", "")),
            expression=str(data.get("expression", "")),
            shot_size=str(data.get("shot_size", "")),
            camera_angle=str(data.get("camera_angle", "")),
            camera_movement=str(data.get("camera_movement", "")),
            background_recipe_id=str(data.get("background_recipe_id", "")),
            background_prompt=str(data.get("background_prompt", "")),
            foreground_effects=tuple(str(value) for value in data.get("foreground_effects", ())),
            transition_in=str(data.get("transition_in", "cut")),
            transition_out=str(data.get("transition_out", "cut")),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            reasoning=str(data.get("reasoning", "")),
            character_pose_asset_ref=str(data.get("character_pose_asset_ref", "")),
            background_asset_ref=str(data.get("background_asset_ref", "")),
        )


@dataclass(frozen=True)
class DirectorScene:
    scene_id: str
    title: str
    location_id: str
    scene_purpose: str
    story_beat: str
    emotional_intent: str
    time_of_day: str
    weather: str
    continuity_notes: tuple[str, ...]
    shots: tuple[DirectorShot, ...]

    def __post_init__(self) -> None:
        _id(self.scene_id, "scene_id")
        _id(self.location_id, "location_id")
        if self.story_beat not in _BEATS or not self.shots:
            raise PreProductionValidationError("Director scene is incomplete.")

    @property
    def start_ms(self) -> int:
        return self.shots[0].start_ms

    @property
    def end_ms(self) -> int:
        return self.shots[-1].end_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "location_id": self.location_id,
            "scene_purpose": self.scene_purpose,
            "story_beat": self.story_beat,
            "emotional_intent": self.emotional_intent,
            "time_of_day": self.time_of_day,
            "weather": self.weather,
            "continuity_notes": list(self.continuity_notes),
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "shots": [shot.to_dict() for shot in self.shots],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DirectorScene":
        return cls(
            scene_id=str(data.get("scene_id", "")),
            title=str(data.get("title", "")),
            location_id=str(data.get("location_id", "")),
            scene_purpose=str(data.get("scene_purpose", "")),
            story_beat=str(data.get("story_beat", "")),
            emotional_intent=str(data.get("emotional_intent", "")),
            time_of_day=str(data.get("time_of_day", "day")),
            weather=str(data.get("weather", "clear")),
            continuity_notes=tuple(str(value) for value in data.get("continuity_notes", ())),
            shots=tuple(DirectorShot.from_dict(item) for item in data.get("shots", ()) if isinstance(item, Mapping)),
        )


@dataclass(frozen=True)
class EpisodeTimelineClip:
    track: str
    clip_id: str
    shot_id: str
    start_frame: int
    duration_frames: int
    label: str
    asset_type: str
    asset_ref: str

    def __post_init__(self) -> None:
        if self.track not in _TRACKS or self.start_frame < 0 or self.duration_frames < 1:
            raise PreProductionValidationError("Timeline clip is invalid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "clip_id": self.clip_id,
            "shot_id": self.shot_id,
            "start_frame": self.start_frame,
            "duration_frames": self.duration_frames,
            "start_ms": round(self.start_frame / 24 * 1000),
            "end_frame": self.start_frame + self.duration_frames,
            "end_ms": round((self.start_frame + self.duration_frames) / 24 * 1000),
            "label": self.label,
            "asset_type": self.asset_type,
            "asset_ref": self.asset_ref,
        }


@dataclass(frozen=True)
class EpisodeDirectorPlan:
    schema_version: int
    episode_id: str
    title: str
    decision_mode: str
    provider: str
    fps: int
    total_duration_seconds: float
    scenes: tuple[DirectorScene, ...]
    character_requirements: tuple[DirectorCharacterRequirement, ...]
    background_requirements: tuple[DirectorBackgroundRequirement, ...]
    timeline: tuple[EpisodeTimelineClip, ...]
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.fps != 24 or not self.scenes or not self.timeline:
            raise PreProductionValidationError("Episode director plan is incomplete.")
        if self.decision_mode not in {"LLM", "RULE_FALLBACK", "HYBRID"}:
            raise PreProductionValidationError("Unknown episode director decision mode.")
        if self.total_duration_seconds <= 0:
            raise PreProductionValidationError("Episode director duration must be positive.")
        shot_clips = [clip for clip in self.timeline if clip.track == "CHARACTER"]
        expected = 0
        for clip in shot_clips:
            if clip.start_frame != expected:
                raise PreProductionValidationError("Character timeline clips must be contiguous.")
            expected += clip.duration_frames
        if expected != round(self.total_duration_seconds * self.fps):
            raise PreProductionValidationError("Timeline duration does not match the episode duration.")

    @property
    def duration_frames(self) -> int:
        return round(self.total_duration_seconds * self.fps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "title": self.title,
            "decision_mode": self.decision_mode,
            "provider": self.provider,
            "fps": self.fps,
            "total_duration_seconds": self.total_duration_seconds,
            "duration_frames": self.duration_frames,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "character_requirements": [item.to_dict() for item in self.character_requirements],
            "background_requirements": [item.to_dict() for item in self.background_requirements],
            "timeline": [item.to_dict() for item in self.timeline],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EpisodeDirectorPlan":
        raw_metadata = data.get("metadata", {})
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            episode_id=str(data.get("episode_id", "")),
            title=str(data.get("title", "")),
            decision_mode=str(data.get("decision_mode", "")),
            provider=str(data.get("provider", "")),
            fps=int(data.get("fps", 0)),
            total_duration_seconds=float(data.get("total_duration_seconds", 0)),
            scenes=tuple(DirectorScene.from_dict(item) for item in data.get("scenes", ()) if isinstance(item, Mapping)),
            character_requirements=tuple(DirectorCharacterRequirement.from_dict(item) for item in data.get("character_requirements", ()) if isinstance(item, Mapping)),
            background_requirements=tuple(DirectorBackgroundRequirement.from_dict(item) for item in data.get("background_requirements", ()) if isinstance(item, Mapping)),
            timeline=tuple(
                EpisodeTimelineClip(
                    track=str(item.get("track", "")),
                    clip_id=str(item.get("clip_id", "")),
                    shot_id=str(item.get("shot_id", "")),
                    start_frame=int(item.get("start_frame", 0)),
                    duration_frames=int(item.get("duration_frames", 0)),
                    label=str(item.get("label", "")),
                    asset_type=str(item.get("asset_type", "")),
                    asset_ref=str(item.get("asset_ref", "")),
                )
                for item in data.get("timeline", ())
                if isinstance(item, Mapping)
            ),
            warnings=tuple(str(value) for value in data.get("warnings", ())),
            metadata=dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {},
        )

    @staticmethod
    def tracks() -> tuple[str, ...]:
        return _TRACKS
