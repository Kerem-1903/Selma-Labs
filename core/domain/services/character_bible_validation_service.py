from __future__ import annotations

from collections.abc import Iterable

from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_bible_validation import (
    CharacterBibleValidationReport,
    InvalidCharacterReference,
)
from core.domain.value_objects.character_identity import ReferenceView


class CharacterBibleValidationService:
    """Validate a portable, production-ready multi-view reference pack."""

    DEFAULT_REQUIRED_VIEWS = (
        ReferenceView.FRONT,
        ReferenceView.PROFILE_LEFT,
        ReferenceView.PROFILE_RIGHT,
        ReferenceView.FACE_CLOSEUP,
        ReferenceView.FULL_BODY,
    )

    def __init__(self, required_views: Iterable[ReferenceView] | None = None) -> None:
        configured = tuple(required_views or self.DEFAULT_REQUIRED_VIEWS)
        if not configured:
            raise ValueError("At least one required reference view must be configured.")
        self._required_views = tuple(dict.fromkeys(configured))

    def validate(self, bible: CharacterBible) -> CharacterBibleValidationReport:
        missing_views = tuple(
            view for view in self._required_views if view not in bible.reference_pack
        )
        invalid_references: list[InvalidCharacterReference] = []

        for pack_view, reference in bible.reference_pack.items():
            reason = self._invalid_reason(bible, pack_view)
            if reason:
                invalid_references.append(
                    InvalidCharacterReference(reference.id, pack_view, reason)
                )

        invalid = tuple(invalid_references)
        return CharacterBibleValidationReport(
            is_complete=not missing_views and not invalid,
            missing_views=missing_views,
            invalid_references=invalid,
        )

    @staticmethod
    def _invalid_reason(bible: CharacterBible, pack_view: ReferenceView) -> str:
        reference = bible.reference_pack[pack_view]
        if reference.character_id != bible.character_id:
            return "Reference belongs to a different character."
        if reference.view != pack_view:
            return "Reference view does not match its reference-pack key."
        if not reference.asset_id.strip():
            return "Reference asset_id is empty."
        if not reference.storage_key.strip():
            return "Reference storage_key is empty."
        if reference.revision < 1:
            return "Reference revision must be greater than zero."
        return ""
