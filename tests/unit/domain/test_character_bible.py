import pytest
from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.style_profile import StyleProfile
from core.domain.value_objects.outfit import Outfit

def test_identity_constraints_serialization():
    constraints = IdentityConstraints(
        eye_color="Brown",
        hair="Black spiky",
        facial_geometry="Angular",
        body_proportions="Athletic",
        silhouette="Tall",
        immutable_marks=["Scar on left cheek"]
    )
    data = constraints.to_dict()
    assert data["eye_color"] == "Brown"
    assert "Scar on left cheek" in data["immutable_marks"]

    restored = IdentityConstraints.from_dict(data)
    assert restored.facial_geometry == "Angular"

def test_character_reference_serialization():
    ref = CharacterReference(
        id="ref_1",
        character_id="akira",
        view=ReferenceView.FRONT,
        asset_id="asset_abc"
    )
    data = ref.to_dict()
    assert data["view"] == "FRONT"

    restored = CharacterReference.from_dict(data)
    assert restored.view == ReferenceView.FRONT
    assert restored.asset_id == "asset_abc"

def test_style_profile_serialization():
    profile = StyleProfile(
        base_style="Anime",
        lighting_preferences=["Cinematic", "High contrast"],
        color_palette=["Red", "Black"],
        negative_prompts=["Ugly", "Blurry"]
    )
    data = profile.to_dict()
    assert data["base_style"] == "Anime"

    restored = StyleProfile.from_dict(data)
    assert "Cinematic" in restored.lighting_preferences

def test_character_bible_initialization():
    constraints = IdentityConstraints("Brown", "Black", "Angular", "Athletic", "Tall")
    profile = StyleProfile("Anime")
    bible = CharacterBible(
        character_id="akira",
        identity_constraints=constraints,
        style_profile=profile,
        schema_version=2
    )
    assert bible.character_id == "akira"
    assert bible.schema_version == 2
    assert bible.identity_constraints.hair == "Black"
    assert len(bible.reference_pack) == 0

def test_character_bible_serialization():
    constraints = IdentityConstraints("Brown", "Black", "Angular", "Athletic", "Tall")
    profile = StyleProfile("Anime")

    ref = CharacterReference(
        id="ref_1",
        character_id="akira",
        view=ReferenceView.FRONT,
        asset_id="asset_abc",
        revision=3,
        content_hash="hash123"
    )
    outfit = Outfit("outfit_1", "akira", "School uniform", ["asset_xyz"])

    bible = CharacterBible(
        character_id="akira",
        identity_constraints=constraints,
        style_profile=profile,
        reference_pack={ReferenceView.FRONT: ref},
        outfit_catalog=[outfit],
        schema_version=2
    )

    data = bible.to_dict()
    assert data["character_id"] == "akira"
    assert data["schema_version"] == 2
    assert data["reference_pack"]["FRONT"]["asset_id"] == "asset_abc"
    assert data["reference_pack"]["FRONT"]["revision"] == 3
    assert data["reference_pack"]["FRONT"]["content_hash"] == "hash123"
    assert len(data["outfit_catalog"]) == 1

    restored = CharacterBible.from_dict(data)
    assert restored.character_id == "akira"
    assert restored.schema_version == 2
    assert ReferenceView.FRONT in restored.reference_pack

    restored_ref = restored.reference_pack[ReferenceView.FRONT]
    assert restored_ref.asset_id == "asset_abc"
    assert restored_ref.revision == 3
    assert restored_ref.content_hash == "hash123"
    assert len(restored.outfit_catalog) == 1
    assert restored.outfit_catalog[0].id == "outfit_1"
