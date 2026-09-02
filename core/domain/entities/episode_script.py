"""Structured screenplay aggregate for locked anime pre-production."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.domain.exceptions import PreProductionValidationError, StoryApprovalError


def _required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return cleaned


class EpisodeScriptStatus(str, Enum):
    DRAFT = "DRAFT"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    LOCKED = "LOCKED"


@dataclass(frozen=True)
class StoryBrief:
    logline: str
    episode_number: int
    target_duration_seconds: int
    language: str = "tr"

    def __post_init__(self) -> None:
        _required(self.logline, "logline")
        _required(self.language, "language")
        if self.episode_number < 1 or self.target_duration_seconds < 15:
            raise PreProductionValidationError(
                "Story brief requires episode >= 1 and duration >= 15 seconds."
            )


@dataclass(frozen=True)
class DialogueLine:
    speaker: str
    text: str

    def __post_init__(self) -> None:
        _required(self.speaker, "dialogue speaker")
        _required(self.text, "dialogue text")

    def to_dict(self) -> dict[str, str]:
        return {"speaker": self.speaker, "text": self.text}


@dataclass(frozen=True)
class AbilityUse:
    character: str
    ability: str

    def __post_init__(self) -> None:
        _required(self.character, "ability character")
        _required(self.ability, "ability")

    def to_dict(self) -> dict[str, str]:
        return {"character": self.character, "ability": self.ability}


@dataclass(frozen=True)
class EpisodeScene:
    id: str
    title: str
    location: str
    summary: str
    characters: tuple[str, ...]
    dialogue: tuple[DialogueLine, ...] = ()
    ability_uses: tuple[AbilityUse, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "scene id"),
            (self.title, "scene title"),
            (self.location, "scene location"),
            (self.summary, "scene summary"),
        ):
            _required(value, name)
        if not self.characters:
            raise PreProductionValidationError(
                "A scene requires at least one character."
            )

    @property
    def full_text(self) -> str:
        return " ".join(
            (self.title, self.summary, *(line.text for line in self.dialogue))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "summary": self.summary,
            "characters": list(self.characters),
            "dialogue": [line.to_dict() for line in self.dialogue],
            "ability_uses": [use.to_dict() for use in self.ability_uses],
        }


@dataclass(frozen=True)
class EpisodeSequence:
    id: str
    title: str
    scenes: tuple[EpisodeScene, ...]

    def __post_init__(self) -> None:
        _required(self.id, "sequence id")
        _required(self.title, "sequence title")
        if not self.scenes:
            raise PreProductionValidationError(
                "A sequence requires at least one scene."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


@dataclass(frozen=True)
class EpisodeScript:
    id: str
    title: str
    logline: str
    episode_number: int
    revision: int
    provider_used: str
    sequences: tuple[EpisodeSequence, ...]
    status: EpisodeScriptStatus
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        logline: str,
        episode_number: int,
        provider_used: str,
        sequences: tuple[EpisodeSequence, ...],
    ) -> EpisodeScript:
        if episode_number < 1 or not sequences:
            raise PreProductionValidationError(
                "Episode script requires episode >= 1 and at least one sequence."
            )
        return cls(
            str(uuid.uuid4()),
            _required(title, "title"),
            _required(logline, "logline"),
            episode_number,
            1,
            _required(provider_used, "provider_used"),
            tuple(sequences),
            EpisodeScriptStatus.DRAFT,
            datetime.now(timezone.utc),
        )

    @property
    def scenes(self) -> tuple[EpisodeScene, ...]:
        return tuple(scene for sequence in self.sequences for scene in sequence.scenes)

    @property
    def full_text(self) -> str:
        return " ".join(
            (self.title, self.logline, *(scene.full_text for scene in self.scenes))
        )

    def with_status(self, status: EpisodeScriptStatus) -> EpisodeScript:
        if self.status is EpisodeScriptStatus.LOCKED:
            raise StoryApprovalError("A locked episode script cannot change status.")
        return replace(self, status=status)

    def lock(self, approved_by: str) -> EpisodeScript:
        if self.status is not EpisodeScriptStatus.READY_FOR_APPROVAL:
            raise StoryApprovalError(
                "Only a review-ready episode script can be locked."
            )
        approver = approved_by.strip()
        if not approver:
            raise StoryApprovalError("approved_by must not be empty.")
        return replace(
            self,
            status=EpisodeScriptStatus.LOCKED,
            approved_by=approver,
            approved_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "logline": self.logline,
            "episode_number": self.episode_number,
            "revision": self.revision,
            "provider_used": self.provider_used,
            "sequences": [sequence.to_dict() for sequence in self.sequences],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeScript:
        sequences = tuple(
            EpisodeSequence(
                id=str(sequence["id"]),
                title=str(sequence["title"]),
                scenes=tuple(
                    EpisodeScene(
                        id=str(scene["id"]),
                        title=str(scene["title"]),
                        location=str(scene["location"]),
                        summary=str(scene["summary"]),
                        characters=tuple(str(value) for value in scene["characters"]),
                        dialogue=tuple(
                            DialogueLine(str(line["speaker"]), str(line["text"]))
                            for line in scene.get("dialogue", [])
                        ),
                        ability_uses=tuple(
                            AbilityUse(str(use["character"]), str(use["ability"]))
                            for use in scene.get("ability_uses", [])
                        ),
                    )
                    for scene in sequence["scenes"]
                ),
            )
            for sequence in data["sequences"]
        )
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            logline=str(data["logline"]),
            episode_number=int(data["episode_number"]),
            revision=int(data["revision"]),
            provider_used=str(data["provider_used"]),
            sequences=sequences,
            status=EpisodeScriptStatus(str(data["status"])),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            approved_by=str(data["approved_by"]) if data.get("approved_by") else None,
            approved_at=datetime.fromisoformat(str(data["approved_at"]))
            if data.get("approved_at")
            else None,
        )
