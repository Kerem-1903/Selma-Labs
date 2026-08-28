from __future__ import annotations

from core.domain.entities.character_bible import CharacterBible
from core.domain.services.character_bible_validation_service import (
    CharacterBibleValidationService,
)
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.style_profile import StyleProfile


def _bible() -> CharacterBible:
    return CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints("Brown", "Black", "Angular", "Athletic", "Tall"),
        style_profile=StyleProfile("Anime"),
    )


def _reference(view: ReferenceView, *, character_id: str = "akira") -> CharacterReference:
    return CharacterReference(
        id=f"ref-{view.value.lower()}",
        character_id=character_id,
        view=view,
        asset_id=f"asset-{view.value.lower()}",
        storage_key=f"characters/akira/references/{view.value.lower()}/asset.png",
        content_type="image/png",
        content_hash="hash",
    )


def test_validation_reports_all_missing_standard_views():
    report = CharacterBibleValidationService().validate(_bible())

    assert report.is_complete is False
    assert report.missing_views == CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS
    assert report.invalid_references == ()


def test_validation_accepts_complete_five_view_pack():
    bible = _bible()
    bible.reference_pack = {
        view: _reference(view)
        for view in CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS
    }

    report = CharacterBibleValidationService().validate(bible)

    assert report.is_complete is True
    assert report.missing_views == ()
    assert report.invalid_references == ()


def test_validation_reports_invalid_reference_separately_from_missing_view():
    bible = _bible()
    bible.reference_pack[ReferenceView.FRONT] = _reference(
        ReferenceView.FRONT,
        character_id="someone-else",
    )

    report = CharacterBibleValidationService(
        required_views=(ReferenceView.FRONT, ReferenceView.PROFILE_LEFT)
    ).validate(bible)

    assert report.is_complete is False
    assert report.missing_views == (ReferenceView.PROFILE_LEFT,)
    assert len(report.invalid_references) == 1
    assert "different character" in report.invalid_references[0].reason
