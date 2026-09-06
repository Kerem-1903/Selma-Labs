"""Series-level style and cast contracts for multi-character anime production."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError

_PORTABLE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _identifier(value: object, field_name: str) -> str:
    identifier = _text(value, field_name).casefold()
    if not _PORTABLE_ID.fullmatch(identifier):
        raise PreProductionValidationError(
            f"{field_name} must contain lowercase letters, numbers and hyphens only."
        )
    return identifier


def _relative_path(value: object, field_name: str) -> str:
    path = PurePosixPath(_text(value, field_name).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise PreProductionValidationError(
            f"{field_name} must stay inside the workspace."
        )
    return path.as_posix()


def _digest(value: object, field_name: str) -> str:
    digest = _text(value, field_name).casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise PreProductionValidationError(f"{field_name} must be a SHA-256 digest.")
    return digest


def _items(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise PreProductionValidationError(f"{field_name} must be a list.")
    items = tuple(_text(item, field_name) for item in value)
    if not items:
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return items


@dataclass(frozen=True)
class SeriesStyleBible:
    style_id: str
    reference_asset: str
    reference_sha256: str
    width: int
    height: int
    status: str
    rendering_rules: tuple[str, ...]
    composition_rules: tuple[str, ...]
    identity_policy: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "style_id", _identifier(self.style_id, "style_id"))
        object.__setattr__(
            self,
            "reference_asset",
            _relative_path(self.reference_asset, "style reference_asset"),
        )
        object.__setattr__(
            self,
            "reference_sha256",
            _digest(self.reference_sha256, "style reference_sha256"),
        )
        if self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError(
                "Style reference dimensions must be positive."
            )
        status = _text(self.status, "style status").upper()
        if status != "APPROVED":
            raise PreProductionValidationError(
                "A production series requires an APPROVED style bible."
            )
        object.__setattr__(self, "status", status)
        for field_name in (
            "rendering_rules",
            "composition_rules",
            "identity_policy",
        ):
            object.__setattr__(
                self, field_name, _items(getattr(self, field_name), field_name)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "reference_asset": self.reference_asset,
            "reference_sha256": self.reference_sha256,
            "width": self.width,
            "height": self.height,
            "status": self.status,
            "rendering_rules": list(self.rendering_rules),
            "composition_rules": list(self.composition_rules),
            "identity_policy": list(self.identity_policy),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SeriesStyleBible:
        return cls(
            style_id=str(data.get("style_id", "")),
            reference_asset=str(data.get("reference_asset", "")),
            reference_sha256=str(data.get("reference_sha256", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            status=str(data.get("status", "")),
            rendering_rules=_items(data.get("rendering_rules", ()), "rendering_rules"),
            composition_rules=_items(
                data.get("composition_rules", ()), "composition_rules"
            ),
            identity_policy=_items(data.get("identity_policy", ()), "identity_policy"),
        )


@dataclass(frozen=True)
class CastMember:
    character_id: str
    version: int
    role: str
    bible_path: str
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "character_id", _identifier(self.character_id, "character_id")
        )
        if self.version < 1:
            raise PreProductionValidationError("Character version must be positive.")
        object.__setattr__(self, "role", _text(self.role, "cast role").casefold())
        object.__setattr__(
            self, "bible_path", _relative_path(self.bible_path, "bible_path")
        )
        status = _text(self.status, "cast status").upper()
        if status not in {"DRAFT", "CANONICAL", "RETIRED"}:
            raise PreProductionValidationError("Unknown cast member status.")
        object.__setattr__(self, "status", status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "version": self.version,
            "role": self.role,
            "bible_path": self.bible_path,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CastMember:
        return cls(
            character_id=str(data.get("character_id", "")),
            version=int(data.get("version", 0)),
            role=str(data.get("role", "")),
            bible_path=str(data.get("bible_path", "")),
            status=str(data.get("status", "")),
        )


@dataclass(frozen=True)
class CharacterRegistry:
    series_id: str
    members: tuple[CastMember, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_id", _identifier(self.series_id, "series_id"))
        keys = [(member.character_id, member.version) for member in self.members]
        if len(keys) != len(set(keys)):
            raise PreProductionValidationError(
                "Character registry contains duplicate character versions."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "series_id": self.series_id,
            "members": [member.to_dict() for member in self.members],
        }

    def register(self, member: CastMember) -> CharacterRegistry:
        key = (member.character_id, member.version)
        if any((item.character_id, item.version) == key for item in self.members):
            raise PreProductionValidationError(
                f"Character {member.character_id} v{member.version} is already registered."
            )
        return CharacterRegistry(series_id=self.series_id, members=(*self.members, member))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterRegistry:
        if int(data.get("schema_version", 0)) != 1:
            raise PreProductionValidationError(
                "Character registry schema_version must be 1."
            )
        raw_members = data.get("members", ())
        if not isinstance(raw_members, (list, tuple)) or not all(
            isinstance(item, Mapping) for item in raw_members
        ):
            raise PreProductionValidationError("members must be a list of objects.")
        return cls(
            series_id=str(data.get("series_id", "")),
            members=tuple(CastMember.from_dict(item) for item in raw_members),
        )


@dataclass(frozen=True)
class SeriesProject:
    series_id: str
    title: str
    style_bible: SeriesStyleBible
    character_registry: str
    model_lock: str
    production_root: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_id", _identifier(self.series_id, "series_id"))
        object.__setattr__(self, "title", _text(self.title, "series title"))
        for field_name in ("character_registry", "model_lock", "production_root"):
            object.__setattr__(
                self,
                field_name,
                _relative_path(getattr(self, field_name), field_name),
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SeriesProject:
        if int(data.get("schema_version", 0)) != 1:
            raise PreProductionValidationError("Series schema_version must be 1.")
        raw_style = data.get("style_bible")
        if not isinstance(raw_style, Mapping):
            raise PreProductionValidationError("style_bible must be an object.")
        return cls(
            series_id=str(data.get("series_id", "")),
            title=str(data.get("title", "")),
            style_bible=SeriesStyleBible.from_dict(raw_style),
            character_registry=str(data.get("character_registry", "")),
            model_lock=str(data.get("model_lock", "")),
            production_root=str(data.get("production_root", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "series_id": self.series_id,
            "title": self.title,
            "style_bible": self.style_bible.to_dict(),
            "character_registry": self.character_registry,
            "model_lock": self.model_lock,
            "production_root": self.production_root,
        }
