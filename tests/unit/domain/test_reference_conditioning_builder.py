import pytest

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_contract import ShotContract
from core.domain.exceptions import ReferenceConditioningError
from core.domain.services.reference_conditioning_builder import ReferenceConditioningBuilder
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)
from core.domain.value_objects.style_profile import StyleProfile


def _contract() -> ShotContract:
    return ShotContract(
        id="shot-1",
        camera_constraints=CameraConstraints("low-angle", "24mm", "tracking"),
        action_constraints=ActionConstraints("draw sword"),
        visual_constraints=VisualConstraints("low-key", "neon street", "rain"),
        required_character_states=[
            CharacterState("akira", "jacket-v2", ["shoulder wound"], ["katana"])
        ],
    )


def _bible(with_reference: bool = True) -> CharacterBible:
    bible = CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints(
            "brown", "black", "angular", "athletic", "tall"
        ),
        style_profile=StyleProfile(
            "anime", negative_prompts=["identity drift", "extra fingers"]
        ),
    )
    if with_reference:
        bible.reference_pack[ReferenceView.FRONT] = CharacterReference(
            id="ref-1",
            character_id="akira",
            view=ReferenceView.FRONT,
            asset_id="asset-front",
            storage_key="characters/akira/front.png",
            content_type="image/png",
            revision=1,
        )
    return bible


def test_builder_combines_identity_continuity_and_portable_references():
    request = ReferenceConditioningBuilder().build(
        shot_contract=_contract(), character_bibles=[_bible()], seed=7
    )

    condition = request.character_conditioning[0]
    assert condition["identity_constraints"]["hair"] == "black"
    assert condition["continuity_state"]["held_objects"] == ["katana"]
    assert request.reference_asset_ids == ("asset-front",)
    assert request.reference_storage_keys == ("characters/akira/front.png",)
    assert request.negative_prompts == ("identity drift", "extra fingers")
    assert request.seed == 7


@pytest.mark.parametrize("bibles,message", [([], "is required"), ([_bible(False)], "no reference")])
def test_builder_rejects_missing_character_conditioning(bibles, message):
    with pytest.raises(ReferenceConditioningError, match=message):
        ReferenceConditioningBuilder().build(
            shot_contract=_contract(), character_bibles=bibles
        )
