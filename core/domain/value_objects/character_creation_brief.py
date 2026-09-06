"""Versioned user input for reference-driven character creation."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from core.domain.exceptions import PreProductionValidationError


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PreProductionValidationError(f"{field_name} must be text.")
    cleaned = value.strip()
    if not cleaned:
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return cleaned


def _optional(value: object, field_name: str = "value") -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PreProductionValidationError(f"{field_name} must be text.")
    return value.strip()


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PreProductionValidationError(f"{field_name} must be an integer.")
    return value


def _items(values: object, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise PreProductionValidationError(f"{field_name} must be a list.")
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise PreProductionValidationError(
                f"{field_name} must contain only text values."
            )
        value = raw.strip()
        folded = value.casefold()
        if value and folded not in seen:
            result.append(value)
            seen.add(folded)
    return tuple(result)


@dataclass(frozen=True)
class CharacterSignatureMark:
    """A visible identity detail that later QC gates may calibrate."""

    label: str
    count: int = 1
    character_side: str = ""
    colour: str = ""

    _SIDES: ClassVar[frozenset[str]] = frozenset(
        {"", "left", "right", "center", "bilateral"}
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _required(self.label, "signature mark label"))
        if self.count < 1:
            raise PreProductionValidationError(
                "signature mark count must be at least 1."
            )
        side = _optional(self.character_side, "signature mark character_side").casefold()
        if side not in self._SIDES:
            raise PreProductionValidationError(
                "signature mark character_side must be left, right, center, or bilateral."
            )
        object.__setattr__(self, "character_side", side)
        object.__setattr__(
            self, "colour", _optional(self.colour, "signature mark colour")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "count": self.count,
            "character_side": self.character_side,
            "colour": self.colour,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterSignatureMark:
        return cls(
            label=data.get("label", ""),
            count=_integer(data.get("count", 1), "signature mark count"),
            character_side=data.get("character_side", ""),
            colour=data.get("colour", ""),
        )


@dataclass(frozen=True)
class CharacterCreationBrief:
    """Confirmed, provider-neutral character design input."""

    schema_version: int
    name: str
    concept: str
    age_band: str = ""
    gender_presentation: str = ""
    body_type: str = ""
    face: str = ""
    eyes: str = ""
    hair: str = ""
    signature_marks: tuple[CharacterSignatureMark, ...] = ()
    outfit: str = ""
    props: tuple[str, ...] = ()
    personality: tuple[str, ...] = ()
    style_preset: str = "selma-anime-v1"
    palette: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    view_pack: str = "standard"
    requested_actions: tuple[str, ...] = ()
    additional_notes: str = ""

    _VIEW_PACKS: ClassVar[frozenset[str]] = frozenset(
        {"minimal", "standard", "extended"}
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "name",
            "concept",
            "age_band",
            "gender_presentation",
            "body_type",
            "face",
            "eyes",
            "hair",
            "signature_marks",
            "outfit",
            "props",
            "personality",
            "style_preset",
            "palette",
            "avoid",
            "view_pack",
            "requested_actions",
            "additional_notes",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "CharacterCreationBrief schema_version must be 1."
            )
        object.__setattr__(self, "name", _required(self.name, "name"))
        object.__setattr__(self, "concept", _required(self.concept, "concept"))
        for field_name in (
            "age_band",
            "gender_presentation",
            "body_type",
            "face",
            "eyes",
            "hair",
            "outfit",
            "additional_notes",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional(getattr(self, field_name), field_name),
            )
        style_preset = _required(self.style_preset, "style_preset")
        object.__setattr__(self, "style_preset", style_preset)
        view_pack = _required(self.view_pack, "view_pack").casefold()
        if view_pack not in self._VIEW_PACKS:
            raise PreProductionValidationError(
                "view_pack must be minimal, standard, or extended."
            )
        object.__setattr__(self, "view_pack", view_pack)
        for field_name in ("props", "personality", "palette", "avoid", "requested_actions"):
            object.__setattr__(
                self, field_name, _items(getattr(self, field_name), field_name)
            )
        marks = tuple(self.signature_marks)
        if not all(isinstance(mark, CharacterSignatureMark) for mark in marks):
            raise PreProductionValidationError(
                "signature_marks must contain CharacterSignatureMark values."
            )
        object.__setattr__(self, "signature_marks", marks)
        conflicts = self.explicit_conflicts()
        if conflicts:
            raise PreProductionValidationError(
                "Character brief contains conflicting selections: "
                + "; ".join(conflicts)
            )

    @property
    def character_id(self) -> str:
        translated = self.name.translate(str.maketrans({"ı": "i", "İ": "I"}))
        ascii_name = unicodedata.normalize("NFKD", translated).encode(
            "ascii", "ignore"
        ).decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
        if slug:
            return slug
        return "character-" + hashlib.sha256(self.name.encode("utf-8")).hexdigest()[:12]

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def explicit_conflicts(self) -> tuple[str, ...]:
        """Detect deterministic conflicts between explicit selections and avoid rules."""
        selected = tuple(
            value
            for value in (
                self.body_type,
                self.face,
                self.eyes,
                self.hair,
                self.outfit,
                *self.props,
                *(mark.label for mark in self.signature_marks),
            )
            if value
        )
        conflicts = []
        for excluded in self.avoid:
            pattern = re.compile(rf"(?<!\w){re.escape(excluded.casefold())}(?!\w)")
            if any(pattern.search(value.casefold()) for value in selected):
                conflicts.append(f"'{excluded}' is both selected and excluded")
        return tuple(conflicts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "concept": self.concept,
            "age_band": self.age_band,
            "gender_presentation": self.gender_presentation,
            "body_type": self.body_type,
            "face": self.face,
            "eyes": self.eyes,
            "hair": self.hair,
            "signature_marks": [mark.to_dict() for mark in self.signature_marks],
            "outfit": self.outfit,
            "props": list(self.props),
            "personality": list(self.personality),
            "style_preset": self.style_preset,
            "palette": list(self.palette),
            "avoid": list(self.avoid),
            "view_pack": self.view_pack,
            "requested_actions": list(self.requested_actions),
            "additional_notes": self.additional_notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterCreationBrief:
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise PreProductionValidationError(
                "CharacterCreationBrief contains unknown fields: " + ", ".join(unknown)
            )
        raw_marks = data.get("signature_marks", ())
        if not isinstance(raw_marks, (list, tuple)):
            raise PreProductionValidationError("signature_marks must be a list.")
        if not all(isinstance(mark, Mapping) for mark in raw_marks):
            raise PreProductionValidationError(
                "signature_marks must contain objects."
            )
        return cls(
            schema_version=_integer(data.get("schema_version", 0), "schema_version"),
            name=data.get("name", ""),
            concept=data.get("concept", ""),
            age_band=data.get("age_band", ""),
            gender_presentation=data.get("gender_presentation", ""),
            body_type=data.get("body_type", ""),
            face=data.get("face", ""),
            eyes=data.get("eyes", ""),
            hair=data.get("hair", ""),
            signature_marks=tuple(
                CharacterSignatureMark.from_dict(mark) for mark in raw_marks
            ),
            outfit=data.get("outfit", ""),
            props=_items(data.get("props"), "props"),
            personality=_items(data.get("personality"), "personality"),
            style_preset=data.get("style_preset", "selma-anime-v1"),
            palette=_items(data.get("palette"), "palette"),
            avoid=_items(data.get("avoid"), "avoid"),
            view_pack=data.get("view_pack", "standard"),
            requested_actions=_items(
                data.get("requested_actions"), "requested_actions"
            ),
            additional_notes=data.get("additional_notes", ""),
        )
