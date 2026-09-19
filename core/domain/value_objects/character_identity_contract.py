"""Shared, provider-neutral visual identity contract for one character version."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from core.domain.value_objects.character_creation_brief import (
    CharacterCreationBrief,
    CharacterSignatureMark,
)


@dataclass(frozen=True)
class CharacterIdentityContract:
    """The immutable visual facts every character-generation path must share.

    This contract intentionally contains no provider syntax, model settings, or
    filesystem paths. It is the bridge between the newer structured brief and
    the legacy Character Bible path while both are still supported.
    """

    schema_version: int
    character_id: str
    concept: str
    age_band: str
    gender_presentation: str
    body_type: str
    face: str
    eyes: str
    hair: str
    signature_marks: tuple[CharacterSignatureMark, ...]
    outfit: str
    props: tuple[str, ...]
    palette: tuple[str, ...]
    style_preset: str
    avoid: tuple[str, ...]
    additional_notes: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("CharacterIdentityContract schema_version must be 1.")
        if not self.character_id.strip():
            raise ValueError("CharacterIdentityContract character_id is required.")
        if not self.concept.strip():
            raise ValueError("CharacterIdentityContract concept is required.")
        if not self.style_preset.strip():
            raise ValueError("CharacterIdentityContract style_preset is required.")
        if not all(isinstance(mark, CharacterSignatureMark) for mark in self.signature_marks):
            raise TypeError("CharacterIdentityContract signature_marks are invalid.")

    @classmethod
    def from_brief(cls, brief: CharacterCreationBrief) -> "CharacterIdentityContract":
        return cls(
            schema_version=1,
            character_id=brief.character_id,
            concept=brief.concept,
            age_band=brief.age_band,
            gender_presentation=brief.gender_presentation,
            body_type=brief.body_type,
            face=brief.face,
            eyes=brief.eyes,
            hair=brief.hair,
            signature_marks=brief.signature_marks,
            outfit=brief.outfit,
            props=brief.props,
            palette=brief.palette,
            style_preset=brief.style_preset,
            avoid=brief.avoid,
            additional_notes=brief.additional_notes,
        )

    @classmethod
    def from_bible(cls, bible: Any) -> "CharacterIdentityContract":
        """Adapt the legacy CharacterBible without importing it here."""
        identity = bible.identity_constraints
        style = bible.style_profile
        outfit = bible.outfit_catalog[0].description if bible.outfit_catalog else ""
        props = tuple(
            fragment
            for fragment in bible.prop_fragments()
            if fragment and fragment not in {outfit}
        )
        marks = tuple(
            CharacterSignatureMark(label=str(mark))
            for mark in identity.immutable_marks
        )
        return cls(
            schema_version=1,
            character_id=bible.character_id,
            concept=(
                bible.narrative_profile.backstory
                if bible.narrative_profile is not None
                else bible.character_id
            ),
            age_band="",
            gender_presentation="",
            body_type=identity.body_proportions,
            face=identity.facial_geometry,
            eyes=f"{identity.eye_color} eyes" if identity.eye_color else "",
            hair=identity.hair,
            signature_marks=marks,
            outfit=outfit or identity.silhouette,
            props=props,
            palette=tuple(style.color_palette),
            style_preset=style.base_style,
            avoid=tuple(style.negative_prompts),
            additional_notes="",
        )

    @property
    def identity_description(self) -> str:
        return ", ".join(
            value
            for value in (
                self.age_band,
                self.gender_presentation,
                self.body_type,
                self.face,
                self.eyes,
                self.hair,
                self.outfit,
                *(mark.label for mark in self.signature_marks),
                *self.props,
            )
            if value
        )

    @property
    def signature_mark_labels(self) -> tuple[str, ...]:
        return tuple(mark.label for mark in self.signature_marks)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def consistency_contract(self, *, style: str | None = None) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "face": self.face,
            "eyes": self.eyes,
            "hair": self.hair,
            "signature_marks": list(self.signature_mark_labels),
            "costume": self.outfit,
            "props": list(self.props),
            "palette": list(self.palette),
            "style": style or self.style_preset,
            "background": "plain light-gray studio background, no scene or dramatic lighting",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
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
            "palette": list(self.palette),
            "style_preset": self.style_preset,
            "avoid": list(self.avoid),
            "additional_notes": self.additional_notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CharacterIdentityContract":
        raw_marks = data.get("signature_marks", ())
        if not isinstance(raw_marks, (list, tuple)):
            raise ValueError("signature_marks must be a list.")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            concept=str(data.get("concept", "")),
            age_band=str(data.get("age_band", "")),
            gender_presentation=str(data.get("gender_presentation", "")),
            body_type=str(data.get("body_type", "")),
            face=str(data.get("face", "")),
            eyes=str(data.get("eyes", "")),
            hair=str(data.get("hair", "")),
            signature_marks=tuple(
                mark if isinstance(mark, CharacterSignatureMark)
                else CharacterSignatureMark.from_dict(mark)
                for mark in raw_marks
            ),
            outfit=str(data.get("outfit", "")),
            props=tuple(str(item) for item in data.get("props", ())),
            palette=tuple(str(item) for item in data.get("palette", ())),
            style_preset=str(data.get("style_preset", "")),
            avoid=tuple(str(item) for item in data.get("avoid", ())),
            additional_notes=str(data.get("additional_notes", "")),
        )
