from __future__ import annotations

from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_identity_contract import (
    CharacterIdentityContract,
)


def _brief() -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Kaito",
            "concept": "Disciplined courier",
            "gender_presentation": "masculine",
            "body_type": "athletic adult",
            "face": "angular anime face",
            "eyes": "steel blue eyes",
            "hair": "short black hair with one cobalt streak",
            "signature_marks": [
                {
                    "label": "single cobalt-blue front hair streak",
                    "character_side": "left",
                    "colour": "#0047AB",
                }
            ],
            "outfit": "charcoal courier jacket with blue trim",
            "props": ["messenger bag on character-right hip"],
            "palette": ["charcoal", "black", "cobalt blue"],
            "style_preset": "selma-anime-v1",
            "avoid": ["chibi proportions"],
        }
    )


def test_contract_from_brief_is_deterministic_and_hash_bound():
    contract = CharacterIdentityContract.from_brief(_brief())

    assert contract.character_id == "kaito"
    assert contract.identity_description.startswith("masculine")
    assert contract.signature_mark_labels == ("single cobalt-blue front hair streak",)
    assert contract.consistency_contract()["costume"] == "charcoal courier jacket with blue trim"
    assert len(contract.content_hash) == 64
    assert contract.content_hash == CharacterIdentityContract.from_dict(
        contract.to_dict()
    ).content_hash


def test_contract_adapts_legacy_character_bible():
    contract = CharacterIdentityContract.from_bible(CharacterBible.akira())

    assert contract.character_id == "akira"
    assert "amber" in contract.eyes
    assert "black" in contract.hair
    assert contract.outfit.startswith("cropped charcoal combat jacket")
    assert "charcoal" in contract.palette
    assert contract.signature_mark_labels
