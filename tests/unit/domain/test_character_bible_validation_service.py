from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.style_profile import StyleProfile
from core.domain.services.character_bible_validation_service import CharacterBibleValidationService

def build_dummy_bible(views_to_include) -> CharacterBible:
    constraints = IdentityConstraints("Brown", "Black", "Angular", "Athletic", "Tall")
    profile = StyleProfile("Anime")

    pack = {}
    for i, view in enumerate(views_to_include):
        pack[view] = CharacterReference(
            id=f"ref_{i}",
            character_id="akira",
            view=view,
            asset_id=f"asset_{i}"
        )

    return CharacterBible(
        character_id="akira",
        identity_constraints=constraints,
        style_profile=profile,
        reference_pack=pack
    )

def test_validate_complete_pack():
    all_views = [
        ReferenceView.FRONT,
        ReferenceView.THREE_QUARTER_LEFT,
        ReferenceView.PROFILE_LEFT,
        ReferenceView.BACK,
        ReferenceView.PROFILE_RIGHT,
        ReferenceView.THREE_QUARTER_RIGHT,
        ReferenceView.FACE_CLOSEUP
    ]
    bible = build_dummy_bible(all_views)
    report = CharacterBibleValidationService.validate(bible)

    assert report.is_complete is True
    assert len(report.missing_views) == 0
    assert len(report.invalid_references) == 0

def test_validate_missing_views():
    partial_views = [
        ReferenceView.FRONT,
        ReferenceView.BACK
    ]
    bible = build_dummy_bible(partial_views)
    report = CharacterBibleValidationService.validate(bible)

    assert report.is_complete is False
    assert ReferenceView.PROFILE_LEFT in report.missing_views
    assert ReferenceView.FRONT not in report.missing_views

def test_validate_invalid_references():
    bible = build_dummy_bible([ReferenceView.FRONT])
    # Manually corrupt the reference
    bible.reference_pack[ReferenceView.FRONT] = CharacterReference(
        id="bad_ref",
        character_id="wrong_char", # Invalid character ID
        view=ReferenceView.FRONT,
        asset_id="" # Missing asset ID
    )

    report = CharacterBibleValidationService.validate(bible)

    assert report.is_complete is False
    assert len(report.invalid_references) == 2
