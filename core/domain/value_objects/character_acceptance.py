"""Character acceptance lists that bind view-pack approval to signed human checks.

A character version's acceptance list is the single source of truth for what a
human operator must confirm before ``view-pack-approval.json`` may be written.
The list is authored per character/version (see ``config/character_acceptance``)
and is enforced by ``CharacterDesignService.approve_view_pack``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PreProductionValidationError(f"{field_name} must be text.")
    cleaned = value.strip()
    if not cleaned:
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return cleaned


def _portable_id(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    if any(character.isspace() or character in "/\\." for character in text):
        raise PreProductionValidationError(
            f"{field_name} must be one portable id segment."
        )
    return text


@dataclass(frozen=True)
class CharacterHumanCheck:
    """One operator-confirmable acceptance item with a stable machine id."""

    id: str
    label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _portable_id(self.id, "human check id"))
        object.__setattr__(
            self, "label", _required_text(self.label, "human check label")
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterHumanCheck:
        return cls(id=str(data.get("id", "")), label=str(data.get("label", "")))


def _text_items(values: object, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise PreProductionValidationError(f"{field_name} must be a list.")
    result: list[str] = []
    for raw in values:
        result.append(_required_text(raw, field_name))
    return tuple(result)


def _evidence_items(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise PreProductionValidationError("required_evidence must be a list.")
    result: list[str] = []
    for raw in values:
        text = _required_text(raw, "required_evidence entry")
        path = PurePosixPath(text)
        if path.is_absolute() or ".." in path.parts:
            raise PreProductionValidationError(
                "required_evidence entries must stay inside the character "
                "version root."
            )
        result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class CharacterAcceptanceList:
    """Schema-validated acceptance list for one character version."""

    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    blocking_policy: str = ""
    automatic_checks: tuple[str, ...] = ()
    human_checks: tuple[CharacterHumanCheck, ...] = ()
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "Character acceptance schema_version must be 1."
            )
        object.__setattr__(
            self,
            "character_id",
            _portable_id(self.character_id, "acceptance character_id"),
        )
        if isinstance(self.character_version, bool) or not isinstance(
            self.character_version, int
        ):
            raise PreProductionValidationError(
                "acceptance character_version must be an integer."
            )
        if self.character_version < 1:
            raise PreProductionValidationError(
                "acceptance character_version must be positive."
            )
        object.__setattr__(
            self, "brief_hash", _required_text(self.brief_hash, "acceptance brief_hash")
        )
        if not isinstance(self.blocking_policy, str):
            raise PreProductionValidationError("blocking_policy must be text.")
        if not self.human_checks:
            raise PreProductionValidationError(
                "Acceptance list requires at least one human check."
            )
        ids = [check.id for check in self.human_checks]
        if len(set(ids)) != len(ids):
            raise PreProductionValidationError(
                "Acceptance human check ids must be unique."
            )
        object.__setattr__(
            self,
            "automatic_checks",
            tuple(
                _portable_id(check, "automatic check id")
                for check in self.automatic_checks
            ),
        )
        if len(set(self.automatic_checks)) != len(self.automatic_checks):
            raise PreProductionValidationError(
                "Acceptance automatic check ids must be unique."
            )
        object.__setattr__(
            self, "required_evidence", _evidence_items(self.required_evidence)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "blocking_policy": self.blocking_policy,
            "automatic_checks": list(self.automatic_checks),
            "human_checks": [check.to_dict() for check in self.human_checks],
            "required_evidence": list(self.required_evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterAcceptanceList:
        raw_automatic_checks = data.get("automatic_checks", ())
        if not isinstance(raw_automatic_checks, (list, tuple)):
            raise PreProductionValidationError("automatic_checks must be a list.")
        raw_checks = data.get("human_checks", ())
        if not isinstance(raw_checks, (list, tuple)):
            raise PreProductionValidationError("human_checks must be a list.")
        human_checks: list[CharacterHumanCheck] = []
        for raw in raw_checks:
            if not isinstance(raw, Mapping):
                raise PreProductionValidationError(
                    "Every human check must be an object with id and label."
                )
            human_checks.append(CharacterHumanCheck.from_dict(raw))
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            brief_hash=str(data.get("brief_hash", "")),
            blocking_policy=str(data.get("blocking_policy", "")),
            automatic_checks=tuple(
                _portable_id(check, "automatic check id")
                for check in raw_automatic_checks
            ),
            human_checks=tuple(human_checks),
            required_evidence=_evidence_items(data.get("required_evidence", ())),
        )

    def content_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_character_acceptance(path: str | Path) -> CharacterAcceptanceList:
    """Load and validate an acceptance list JSON file."""
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("Character acceptance JSON must contain an object.")
    return CharacterAcceptanceList.from_dict(payload)


def acceptance_file_digest(path: str | Path) -> str:
    """SHA-256 of the exact acceptance file bytes used for the approval binding."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
