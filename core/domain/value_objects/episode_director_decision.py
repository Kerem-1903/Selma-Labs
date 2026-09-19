"""Validated semantic decisions for the optional Episode Director provider."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.domain.exceptions import PreProductionValidationError

_ALLOWED_BEATS = frozenset({"setup", "context", "conflict", "reveal", "reaction", "transition", "payoff"})
_ALLOWED_POSES = frozenset({"FRONT_NEUTRAL", "PROFILE_LEFT", "BACK_FULL_BODY"})
_ALLOWED_SHOTS = frozenset({"wide", "medium", "close_up", "profile", "insert"})


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{name} must not be empty.")
    return value.strip()


@dataclass(frozen=True)
class EpisodeSceneDecision:
    scene_id: str
    purpose: str
    story_beat: str
    emotional_intent: str
    character_actions: Mapping[str, str] = field(default_factory=dict)
    pose_preferences: Mapping[str, str] = field(default_factory=dict)
    shot_sizes: tuple[str, ...] = ()
    background_direction: str = ""

    def __post_init__(self) -> None:
        _required(self.scene_id, "scene_id")
        _required(self.purpose, "purpose")
        _required(self.emotional_intent, "emotional_intent")
        if self.story_beat not in _ALLOWED_BEATS:
            raise PreProductionValidationError(f"Unsupported story beat: {self.story_beat}")
        for character_id, action in self.character_actions.items():
            _required(character_id, "character action character")
            _required(action, "character action")
        for character_id, pose in self.pose_preferences.items():
            _required(character_id, "pose preference character")
            if pose not in _ALLOWED_POSES:
                raise PreProductionValidationError(f"Unsupported pose preference: {pose}")
        if any(size not in _ALLOWED_SHOTS for size in self.shot_sizes):
            raise PreProductionValidationError("Unsupported shot size in director decision.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "purpose": self.purpose,
            "story_beat": self.story_beat,
            "emotional_intent": self.emotional_intent,
            "character_actions": dict(self.character_actions),
            "pose_preferences": dict(self.pose_preferences),
            "shot_sizes": list(self.shot_sizes),
            "background_direction": self.background_direction,
        }


@dataclass(frozen=True)
class EpisodeDirectorDecision:
    decisions: tuple[EpisodeSceneDecision, ...]
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.decisions:
            raise PreProductionValidationError("Director provider returned no scene decisions.")
        scene_ids = [decision.scene_id for decision in self.decisions]
        if len(scene_ids) != len(set(scene_ids)):
            raise PreProductionValidationError("Director decisions contain duplicate scene IDs.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "rationale": self.rationale,
        }
