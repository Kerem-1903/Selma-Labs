"""Immutable manifest for one fully specified animation-ready shot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import AnimationPackageError


def _portable(value: str, field_name: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AnimationPackageError(f"{field_name} must be a portable relative key.")
    return normalized


@dataclass(frozen=True)
class ShotPackageSources:
    start_keyframe: str
    end_keyframe: str
    background_clean: str
    character_mask: str
    dialogue_audio: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.start_keyframe,
                self.end_keyframe,
                self.background_clean,
                self.character_mask,
                self.dialogue_audio,
            )
        ):
            raise AnimationPackageError("Every animation package source is required.")
        for field_name in (
            "start_keyframe",
            "end_keyframe",
            "background_clean",
            "character_mask",
            "dialogue_audio",
        ):
            _portable(getattr(self, field_name), field_name)

    @property
    def all_keys(self) -> tuple[str, ...]:
        return (
            self.start_keyframe,
            self.end_keyframe,
            self.background_clean,
            self.character_mask,
            self.dialogue_audio,
        )


@dataclass(frozen=True)
class AnimationReadyPackage:
    shot_id: str
    package_root: str
    shot_contract_key: str
    start_keyframe_key: str
    end_keyframe_key: str
    background_clean_key: str
    character_mask_key: str
    dialogue_audio_key: str
    effects_spec_key: str
    created_at: datetime

    @classmethod
    def create(cls, *, shot_id: str, package_root: str) -> AnimationReadyPackage:
        if not shot_id.strip() or not package_root.strip():
            raise AnimationPackageError("Animation package identity is incomplete.")
        root = _portable(package_root.rstrip("/"), "package_root")
        return cls(
            shot_id,
            root,
            f"{root}/shot-contract.json",
            f"{root}/start-keyframe.png",
            f"{root}/end-keyframe.png",
            f"{root}/background-clean.png",
            f"{root}/character-mask.png",
            f"{root}/dialogue.wav",
            f"{root}/effects-spec.json",
            datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "package_root": self.package_root,
            "shot_contract_key": self.shot_contract_key,
            "start_keyframe_key": self.start_keyframe_key,
            "end_keyframe_key": self.end_keyframe_key,
            "background_clean_key": self.background_clean_key,
            "character_mask_key": self.character_mask_key,
            "dialogue_audio_key": self.dialogue_audio_key,
            "effects_spec_key": self.effects_spec_key,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimationReadyPackage:
        return cls(
            shot_id=str(data["shot_id"]),
            package_root=str(data["package_root"]),
            shot_contract_key=str(data["shot_contract_key"]),
            start_keyframe_key=str(data["start_keyframe_key"]),
            end_keyframe_key=str(data["end_keyframe_key"]),
            background_clean_key=str(data["background_clean_key"]),
            character_mask_key=str(data["character_mask_key"]),
            dialogue_audio_key=str(data["dialogue_audio_key"]),
            effects_spec_key=str(data["effects_spec_key"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )
