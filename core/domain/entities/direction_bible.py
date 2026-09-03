"""Versioned creative, world, and visual direction bibles."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from core.domain.exceptions import PreProductionValidationError


class BibleStatus(str, Enum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


def _required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return cleaned


def _items(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(frozen=True)
class CreativeDirectionBible:
    id: str
    title: str
    version: int
    genre: str
    target_audience: str
    narrative_tone: tuple[str, ...]
    visual_identity: str
    originality_guardrails: tuple[str, ...] = ()
    status: BibleStatus = BibleStatus.DRAFT

    @classmethod
    def create(
        cls,
        *,
        title: str,
        version: int,
        genre: str,
        target_audience: str,
        narrative_tone: tuple[str, ...],
        visual_identity: str,
        originality_guardrails: tuple[str, ...] = (),
    ) -> CreativeDirectionBible:
        tones = _items(narrative_tone)
        if version < 1 or not tones:
            raise PreProductionValidationError(
                "Creative direction requires a positive version and narrative tone."
            )
        return cls(
            str(uuid.uuid4()),
            _required(title, "title"),
            version,
            _required(genre, "genre"),
            _required(target_audience, "target_audience"),
            tones,
            _required(visual_identity, "visual_identity"),
            _items(originality_guardrails),
        )

    def lock(self) -> CreativeDirectionBible:
        return replace(self, status=BibleStatus.LOCKED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "version": self.version,
            "genre": self.genre,
            "target_audience": self.target_audience,
            "narrative_tone": list(self.narrative_tone),
            "visual_identity": self.visual_identity,
            "originality_guardrails": list(self.originality_guardrails),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreativeDirectionBible:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            version=int(data["version"]),
            genre=str(data["genre"]),
            target_audience=str(data["target_audience"]),
            narrative_tone=tuple(str(value) for value in data["narrative_tone"]),
            visual_identity=str(data["visual_identity"]),
            originality_guardrails=tuple(
                str(value) for value in data.get("originality_guardrails", [])
            ),
            status=BibleStatus(str(data["status"])),
        )


@dataclass(frozen=True)
class WorldRule:
    id: str
    description: str
    forbidden_phrases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required(self.id, "world rule id")
        _required(self.description, "world rule description")
        object.__setattr__(self, "forbidden_phrases", _items(self.forbidden_phrases))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "forbidden_phrases": list(self.forbidden_phrases),
        }


@dataclass(frozen=True)
class LocationDefinition:
    id: str
    name: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required(self.id, "location id")
        _required(self.name, "location name")
        object.__setattr__(self, "aliases", _items(self.aliases))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "aliases": list(self.aliases)}


@dataclass(frozen=True)
class WorldBible:
    id: str
    name: str
    version: int
    premise: str
    locations: tuple[LocationDefinition, ...]
    rules: tuple[WorldRule, ...]
    status: BibleStatus = BibleStatus.DRAFT

    @classmethod
    def create(
        cls,
        *,
        name: str,
        version: int,
        premise: str,
        locations: tuple[LocationDefinition, ...],
        rules: tuple[WorldRule, ...],
    ) -> WorldBible:
        if version < 1 or not locations:
            raise PreProductionValidationError(
                "World bible requires a positive version and at least one location."
            )
        location_ids = [location.id.casefold() for location in locations]
        rule_ids = [rule.id.casefold() for rule in rules]
        if len(location_ids) != len(set(location_ids)) or len(rule_ids) != len(
            set(rule_ids)
        ):
            raise PreProductionValidationError(
                "World bible identifiers must be unique."
            )
        return cls(
            str(uuid.uuid4()),
            _required(name, "name"),
            version,
            _required(premise, "premise"),
            tuple(locations),
            tuple(rules),
        )

    def lock(self) -> WorldBible:
        return replace(self, status=BibleStatus.LOCKED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "premise": self.premise,
            "locations": [location.to_dict() for location in self.locations],
            "rules": [rule.to_dict() for rule in self.rules],
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldBible:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=int(data["version"]),
            premise=str(data["premise"]),
            locations=tuple(
                LocationDefinition(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    aliases=tuple(str(value) for value in item.get("aliases", [])),
                )
                for item in data["locations"]
            ),
            rules=tuple(
                WorldRule(
                    id=str(item["id"]),
                    description=str(item["description"]),
                    forbidden_phrases=tuple(
                        str(value) for value in item.get("forbidden_phrases", [])
                    ),
                )
                for item in data.get("rules", [])
            ),
            status=BibleStatus(str(data["status"])),
        )


@dataclass(frozen=True)
class VisualStyleBible:
    id: str
    name: str
    version: int
    palette: tuple[str, ...]
    line_language: str
    shading_language: str
    camera_language: str
    prohibited_traits: tuple[str, ...] = ()
    status: BibleStatus = BibleStatus.DRAFT

    @classmethod
    def create(
        cls,
        *,
        name: str,
        version: int,
        palette: tuple[str, ...],
        line_language: str,
        shading_language: str,
        camera_language: str,
        prohibited_traits: tuple[str, ...] = (),
    ) -> VisualStyleBible:
        colors = _items(palette)
        if version < 1 or not colors:
            raise PreProductionValidationError(
                "Visual style requires a positive version and palette."
            )
        return cls(
            str(uuid.uuid4()),
            _required(name, "name"),
            version,
            colors,
            _required(line_language, "line_language"),
            _required(shading_language, "shading_language"),
            _required(camera_language, "camera_language"),
            _items(prohibited_traits),
        )

    def lock(self) -> VisualStyleBible:
        return replace(self, status=BibleStatus.LOCKED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "palette": list(self.palette),
            "line_language": self.line_language,
            "shading_language": self.shading_language,
            "camera_language": self.camera_language,
            "prohibited_traits": list(self.prohibited_traits),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualStyleBible:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=int(data["version"]),
            palette=tuple(str(value) for value in data["palette"]),
            line_language=str(data["line_language"]),
            shading_language=str(data["shading_language"]),
            camera_language=str(data["camera_language"]),
            prohibited_traits=tuple(
                str(value) for value in data.get("prohibited_traits", [])
            ),
            status=BibleStatus(str(data["status"])),
        )
