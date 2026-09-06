from __future__ import annotations

import pytest

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_creation_brief import (
    CharacterCreationBrief,
    CharacterSignatureMark,
)


def _payload() -> dict:
    return {
        "schema_version": 1,
        "name": "Mira",
        "concept": "Underground courier who manipulates sound",
        "age_band": "young adult",
        "gender_presentation": "feminine",
        "body_type": "lean athletic",
        "face": "angular face, soft jaw",
        "eyes": "amber, narrow",
        "hair": "black bob with exactly one red lock",
        "signature_marks": [
            {
                "label": "red hair lock",
                "count": 1,
                "character_side": "left",
                "colour": "#9E2838",
            }
        ],
        "outfit": "cropped courier jacket and black boots",
        "props": ["folding baton"],
        "personality": ["alert", "restrained"],
        "style_preset": "selma-anime-v1",
        "palette": ["charcoal", "burgundy", "amber"],
        "avoid": ["cape", "tattoos"],
        "view_pack": "standard",
        "requested_actions": ["walking", "running", "guard"],
        "additional_notes": "Keep the silhouette readable.",
    }


def test_brief_round_trips_and_has_stable_identity_and_hash():
    brief = CharacterCreationBrief.from_dict(_payload())
    restored = CharacterCreationBrief.from_dict(brief.to_dict())

    assert restored == brief
    assert brief.character_id == "mira"
    assert restored.content_hash == brief.content_hash
    assert len(brief.content_hash) == 64


def test_brief_only_requires_name_and_concept():
    brief = CharacterCreationBrief.from_dict(
        {"schema_version": 1, "name": "Ada", "concept": "Sky mechanic"}
    )

    assert brief.view_pack == "standard"
    assert brief.style_preset == "selma-anime-v1"
    assert brief.props == ()


def test_brief_normalizes_turkish_name_and_deduplicates_lists():
    payload = _payload()
    payload["name"] = "Işık Şahin"
    payload["props"] = ["Baton", " baton ", ""]

    brief = CharacterCreationBrief.from_dict(payload)

    assert brief.character_id == "isik-sahin"
    assert brief.props == ("Baton",)


@pytest.mark.parametrize("field", ["name", "concept"])
def test_brief_rejects_missing_required_fields(field):
    payload = _payload()
    payload[field] = " "

    with pytest.raises(PreProductionValidationError, match=field):
        CharacterCreationBrief.from_dict(payload)


def test_brief_rejects_selected_and_excluded_feature_conflict():
    payload = _payload()
    payload["outfit"] = "burgundy cape and black boots"
    payload["avoid"] = ["cape"]

    with pytest.raises(PreProductionValidationError, match="both selected and excluded"):
        CharacterCreationBrief.from_dict(payload)


def test_brief_rejects_unknown_fields_instead_of_ignoring_typo():
    payload = _payload()
    payload["hairstyle"] = "short"

    with pytest.raises(PreProductionValidationError, match="hairstyle"):
        CharacterCreationBrief.from_dict(payload)


def test_signature_mark_rejects_invalid_count_and_side():
    with pytest.raises(PreProductionValidationError, match="at least 1"):
        CharacterSignatureMark("scar", count=0)
    with pytest.raises(PreProductionValidationError, match="character_side"):
        CharacterSignatureMark("scar", character_side="viewer-left")


def test_content_hash_changes_when_confirmed_input_changes():
    first = CharacterCreationBrief.from_dict(_payload())
    changed = _payload()
    changed["hair"] = "silver bob"
    second = CharacterCreationBrief.from_dict(changed)

    assert first.content_hash != second.content_hash


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", 42, "name must be text"),
        ("schema_version", "1", "schema_version must be an integer"),
        ("props", [{"name": "baton"}], "props must contain only text"),
    ],
)
def test_brief_rejects_wrong_user_input_types(field, value, message):
    payload = _payload()
    payload[field] = value

    with pytest.raises(PreProductionValidationError, match=message):
        CharacterCreationBrief.from_dict(payload)
