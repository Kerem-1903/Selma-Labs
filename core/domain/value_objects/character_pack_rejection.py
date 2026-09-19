"""Fail-closed human rejection receipts for character reference packs.

A rejection is a verdict, not a note. Before this existed a pack a human had
turned down stayed ``PENDING_HUMAN_REVIEW`` on disk, so any later run could
still approve it and the refusal lived only in someone's memory. The approval
gates now read this receipt and refuse.

The only way past a rejection is a new character version: the receipt is bound
to one ``(character_id, character_version, artifact)`` triple, and editing it
to reopen a rejected pack is exactly the move it exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.domain.exceptions import PreProductionValidationError

REJECTION_SCHEMA_VERSION = 1
REJECTED_ARTIFACTS = ("VIEW_PACK", "POSE_PACK")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    text = _text(value, field_name).casefold()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise PreProductionValidationError(f"{field_name} must be a SHA-256 digest.")
    return text


@dataclass(frozen=True)
class CharacterPackRejection:
    """One human refusal of one character version's pack."""

    schema_version: int
    character_id: str
    character_version: int
    artifact: str
    reason: str
    rejected_by: str
    rejected_at: datetime
    rejected_hashes: Mapping[str, str]
    superseded_by_version: int | None = None

    def __post_init__(self) -> None:
        if self.schema_version != REJECTION_SCHEMA_VERSION:
            raise PreProductionValidationError(
                "Unsupported character pack rejection schema version."
            )
        object.__setattr__(self, "character_id", _text(self.character_id, "character_id"))
        object.__setattr__(self, "artifact", _text(self.artifact, "artifact").upper())
        object.__setattr__(self, "rejected_by", _text(self.rejected_by, "rejected_by"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if self.artifact not in REJECTED_ARTIFACTS:
            raise PreProductionValidationError(
                f"artifact must be one of {', '.join(REJECTED_ARTIFACTS)}."
            )
        if self.character_version < 1:
            raise PreProductionValidationError(
                "A rejection must name the character version it refuses."
            )
        if self.superseded_by_version is not None and (
            self.superseded_by_version <= self.character_version
        ):
            raise PreProductionValidationError(
                "A replacement version must be newer than the rejected version."
            )
        for name, digest in self.rejected_hashes.items():
            _hash(digest, f"rejected_hashes[{name}]")

    @property
    def storage_filename(self) -> str:
        """Receipt filename inside the pack's own directory."""
        return (
            "view-pack-rejection.json"
            if self.artifact == "VIEW_PACK"
            else "rejection.json"
        )

    def refusal_message(self, *, attempted_version: int | None = None) -> str:
        """The message an approval gate raises when it meets this receipt."""
        where = (
            f"v{attempted_version}"
            if attempted_version is not None
            else f"v{self.character_version}"
        )
        message = (
            f"Character '{self.character_id}' {where} {self.artifact} was rejected "
            f"by {self.rejected_by} on {self.rejected_at.date().isoformat()}: "
            f"{self.reason} A rejected pack cannot be approved; produce a newer "
            f"character version instead."
        )
        if self.superseded_by_version is not None:
            message += f" Its replacement is v{self.superseded_by_version}."
        return message

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "artifact": self.artifact,
            "reason": self.reason,
            "rejected_by": self.rejected_by,
            "rejected_at": self.rejected_at.isoformat(),
            "human_rejected": True,
            "rejected_hashes": dict(self.rejected_hashes),
            "superseded_by_version": self.superseded_by_version,
            "next_gate": "NEW_CHARACTER_VERSION",
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterPackRejection:
        raw_hashes = data.get("rejected_hashes", {})
        raw_superseded = data.get("superseded_by_version")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            artifact=str(data.get("artifact", "")),
            reason=str(data.get("reason", "")),
            rejected_by=str(data.get("rejected_by", "")),
            rejected_at=datetime.fromisoformat(str(data.get("rejected_at", ""))),
            rejected_hashes=(
                {str(key): str(value) for key, value in raw_hashes.items()}
                if isinstance(raw_hashes, Mapping)
                else {}
            ),
            superseded_by_version=(
                int(raw_superseded) if raw_superseded is not None else None
            ),
        )
