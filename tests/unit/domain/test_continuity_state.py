from core.domain.entities.character_state import CharacterState
from core.domain.entities.continuity_state import ContinuityState

def test_continuity_state_initialization():
    state = ContinuityState(id="world_1")
    assert state.id == "world_1"
    assert len(state.world_snapshot) == 0

def test_continuity_state_update():
    cont_state = ContinuityState(id="world_1")
    char_state = CharacterState(
        character_id="char_1",
        active_outfit_id="outfit_2",
        injuries=[],
        held_objects=[]
    )
    cont_state.update_character(char_state)
    assert "char_1" in cont_state.world_snapshot
    assert cont_state.world_snapshot["char_1"].active_outfit_id == "outfit_2"

def test_continuity_state_serialization():
    cont_state = ContinuityState(id="world_1")
    char_state = CharacterState(
        character_id="char_1",
        active_outfit_id="outfit_2",
        injuries=[],
        held_objects=[]
    )
    cont_state.update_character(char_state)

    data = cont_state.to_dict()
    assert "world_snapshot" in data
    assert "char_1" in data["world_snapshot"]

    restored = ContinuityState.from_dict(data)
    assert restored.id == "world_1"
    assert restored.world_snapshot["char_1"].active_outfit_id == "outfit_2"
