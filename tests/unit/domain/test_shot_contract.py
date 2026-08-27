from core.domain.entities.shot_contract import ShotContract
from core.domain.entities.character_state import CharacterState
from core.domain.value_objects.shot_constraints import CameraConstraints, ActionConstraints, VisualConstraints

def test_shot_contract_initialization():
    camera = CameraConstraints(angle="low-angle", lens="24mm", movement="static")
    action = ActionConstraints(primary_action="running", secondary_actions=[])
    visual = VisualConstraints(lighting="dark lighting", environment_style="cyberpunk", weather="rain")

    contract = ShotContract(
        id="shot_1",
        camera_constraints=camera,
        action_constraints=action,
        visual_constraints=visual
    )
    assert contract.id == "shot_1"
    assert contract.camera_constraints.angle == "low-angle"
    assert contract.action_constraints.primary_action == "running"
    assert contract.visual_constraints.weather == "rain"
    assert len(contract.required_character_states) == 0

def test_shot_contract_has_no_prompt_field():
    camera = CameraConstraints(angle="low-angle", lens="24mm", movement="static")
    action = ActionConstraints(primary_action="running", secondary_actions=[])
    visual = VisualConstraints(lighting="dark lighting", environment_style="cyberpunk", weather="rain")

    contract = ShotContract(
        id="shot_1",
        camera_constraints=camera,
        action_constraints=action,
        visual_constraints=visual
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
    camera = CameraConstraints(angle="low-angle", lens="24mm", movement="static")
    action = ActionConstraints(primary_action="running", secondary_actions=[])
    visual = VisualConstraints(lighting="dark lighting", environment_style="cyberpunk", weather="rain")

    contract = ShotContract(
        id="shot_1",
        camera_constraints=camera,
        action_constraints=action,
        visual_constraints=visual,
        required_character_states=[char_state]
    )

    data = contract.to_dict()
    assert data["id"] == "shot_1"
    assert data["camera_constraints"]["angle"] == "low-angle"
    assert len(data["required_character_states"]) == 1

    restored = ShotContract.from_dict(data)
    assert restored.camera_constraints.angle == "low-angle"
    assert restored.action_constraints.primary_action == "running"
    assert restored.visual_constraints.lighting == "dark lighting"
    assert len(restored.required_character_states) == 1
    assert restored.required_character_states[0].character_id == "char_1"
