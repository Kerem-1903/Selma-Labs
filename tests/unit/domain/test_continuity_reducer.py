import pytest
from core.domain.entities.continuity_state import ContinuityState
from core.domain.entities.character_state import CharacterState
from core.domain.services.continuity_reducer import ContinuityReducer
from core.domain.events.continuity_event import (
    OutfitDamaged,
    CharacterPickedUpObject,
    ObjectBroken,
    CharacterDroppedObject
)

def test_akira_timeline_replay():
    # Akira starts with intact battle jacket
    initial_state = ContinuityState(id="world_1")
    initial_state.update_character(CharacterState(
        character_id="akira",
        active_outfit_id="battle_v1",
        injuries=[],
        held_objects=[],
        location="street",
        emotion="neutral",
        outfit_damage={}
    ))

    # Define events chronologically
    events = [
        OutfitDamaged("OutfitDamaged", 1, 10, "SH_038", "akira", "battle_v1", "left_sleeve"),
        CharacterPickedUpObject("CharacterPickedUpObject", 1, 20, "SH_041", "akira", "katana_01"),
        ObjectBroken("ObjectBroken", 1, 30, "SH_052", "katana_01")
    ]

    # Replay timeline
    final_state = ContinuityReducer.replay(initial_state, events)

    # Assertions
    akira = final_state.world_snapshot["akira"]
    assert akira.outfit_damage.get("left_sleeve") == "torn"
    assert "katana_01" in akira.held_objects
    assert final_state.object_states.get("katana_01") == "broken"

def test_invalid_drop_raises_error():
    initial_state = ContinuityState(id="world_1")
    event = CharacterDroppedObject("CharacterDroppedObject", 1, 10, "SH_001", "akira", "ghost_sword")

    with pytest.raises(ValueError, match="Cannot drop object"):
        ContinuityReducer.apply(initial_state, event)

def test_invalid_break_raises_error():
    initial_state = ContinuityState(id="world_1")
    event = ObjectBroken("ObjectBroken", 1, 10, "SH_001", "ghost_sword")

    with pytest.raises(ValueError, match="Cannot break object"):
        ContinuityReducer.apply(initial_state, event)

def test_invalid_outfit_damage_raises_error():
    initial_state = ContinuityState(id="world_1")
    initial_state.update_character(CharacterState(
        character_id="akira",
        active_outfit_id="casual",
        injuries=[],
        held_objects=[],
        outfit_damage={}
    ))

    event = OutfitDamaged("OutfitDamaged", 1, 10, "SH_001", "akira", "battle_v1", "left_sleeve")
    with pytest.raises(ValueError, match="Cannot damage outfit"):
        ContinuityReducer.apply(initial_state, event)
