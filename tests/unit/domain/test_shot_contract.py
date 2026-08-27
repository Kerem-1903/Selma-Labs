from core.domain.entities.shot_contract import ShotContract
from core.domain.entities.character_state import CharacterState

def test_shot_contract_initialization():
    contract = ShotContract(
        id="shot_1",
        camera_constraints="low-angle 24mm",
        action_constraints="running",
        visual_constraints="dark lighting"
    )
    assert contract.id == "shot_1"
    assert contract.camera_constraints == "low-angle 24mm"
    assert len(contract.required_character_states) == 0

def test_shot_contract_has_no_prompt_field():
    contract = ShotContract(
        id="shot_1",
        camera_constraints="low-angle 24mm",
        action_constraints="running",
        visual_constraints="dark lighting"
    )
    # The prompt should not exist on the domain entity.
    assert not hasattr(contract, "prompt")

def test_shot_contract_serialization():
    char_state = CharacterState(
        character_id="char_1",
        active_outfit_id="outfit_1",
        injuries=[],
        held_objects=[]
    )
    contract = ShotContract(
        id="shot_1",
        camera_constraints="low-angle",
        action_constraints="standing",
        visual_constraints="bright",
        required_character_states=[char_state]
    )

    data = contract.to_dict()
    assert data["id"] == "shot_1"
    assert len(data["required_character_states"]) == 1

    restored = ShotContract.from_dict(data)
    assert restored.camera_constraints == "low-angle"
    assert len(restored.required_character_states) == 1
    assert restored.required_character_states[0].character_id == "char_1"
