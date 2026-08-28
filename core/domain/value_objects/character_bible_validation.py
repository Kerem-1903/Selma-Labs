from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects.character_identity import ReferenceView


@dataclass(frozen=True)
class InvalidCharacterReference:
    reference_id: str
    view: ReferenceView
    reason: str


@dataclass(frozen=True)
class CharacterBibleValidationReport:
    is_complete: bool
    missing_views: tuple[ReferenceView, ...]
    invalid_references: tuple[InvalidCharacterReference, ...]
