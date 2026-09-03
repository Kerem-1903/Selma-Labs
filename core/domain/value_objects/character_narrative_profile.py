"""Narrative canon attached to a visual CharacterBible."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError


def _items(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(frozen=True)
class CharacterNarrativeProfile:
    canonical_names: tuple[str, ...]
    motivation: str
    backstory: str
    voice_traits: tuple[str, ...]
    allowed_abilities: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    forbidden_voice_phrases: tuple[str, ...] = ()
    locked: bool = False

    def __post_init__(self) -> None:
        names = _items(self.canonical_names)
        if not names:
            raise PreProductionValidationError(
                "Character narrative profile requires at least one canonical name."
            )
        if not self.motivation.strip() or not self.backstory.strip():
            raise PreProductionValidationError(
                "Character narrative profile requires motivation and backstory."
            )
        object.__setattr__(self, "canonical_names", names)
        for field_name in (
            "voice_traits",
            "allowed_abilities",
            "forbidden_behaviors",
            "forbidden_voice_phrases",
        ):
            object.__setattr__(self, field_name, _items(getattr(self, field_name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_names": list(self.canonical_names),
            "motivation": self.motivation,
            "backstory": self.backstory,
            "voice_traits": list(self.voice_traits),
            "allowed_abilities": list(self.allowed_abilities),
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "forbidden_voice_phrases": list(self.forbidden_voice_phrases),
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterNarrativeProfile:
        return cls(
            canonical_names=tuple(str(value) for value in data["canonical_names"]),
            motivation=str(data["motivation"]),
            backstory=str(data["backstory"]),
            voice_traits=tuple(str(value) for value in data.get("voice_traits", [])),
            allowed_abilities=tuple(
                str(value) for value in data.get("allowed_abilities", [])
            ),
            forbidden_behaviors=tuple(
                str(value) for value in data.get("forbidden_behaviors", [])
            ),
            forbidden_voice_phrases=tuple(
                str(value) for value in data.get("forbidden_voice_phrases", [])
            ),
            locked=bool(data.get("locked", False)),
        )
