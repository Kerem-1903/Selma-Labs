from core.domain.entities.character_state import CharacterState

def test_character_state_initialization():
    state = CharacterState(
        character_id="char_1",
        active_outfit_id="outfit_1",
        injuries=["cut on right cheek"],
        held_objects=["broken sword"]
    )
    assert state.character_id == "char_1"
    assert "cut on right cheek" in state.injuries
    assert "broken sword" in state.held_objects

def test_character_state_serialization():
    state = CharacterState(
        character_id="char_1",
        active_outfit_id="outfit_1",
        injuries=["scar"],
        held_objects=["gun"]
    )
    data = state.to_dict()
    assert data["active_outfit_id"] == "outfit_1"

    state_restored = CharacterState.from_dict(data)
    assert state_restored.character_id == "char_1"
    assert "scar" in state_restored.injuries
