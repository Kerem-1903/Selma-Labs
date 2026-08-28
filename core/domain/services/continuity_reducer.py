from typing import List
import copy
from core.domain.entities.continuity_state import ContinuityState
from core.domain.entities.character_state import CharacterState
from core.domain.events.continuity_event import (
    ContinuityEvent,
    CharacterEnteredLocation,
    CharacterChangedOutfit,
    CharacterPickedUpObject,
    CharacterDroppedObject,
    CharacterInjured,
    OutfitDamaged,
    ObjectBroken,
    CharacterEmotionChanged
)

class ContinuityReducer:
    @staticmethod
    def apply(state: ContinuityState, event: ContinuityEvent) -> ContinuityState:
        # Create a deep copy to ensure immutability/pure function behavior
        new_state = copy.deepcopy(state)

        # Helper to get or initialize a character's state
        def _get_or_create_character_state(char_id: str) -> CharacterState:
            if char_id not in new_state.world_snapshot:
                new_state.world_snapshot[char_id] = CharacterState(
                    character_id=char_id,
                    active_outfit_id="default",
                    injuries=[],
                    held_objects=[],
                    location="unknown",
                    emotion="neutral",
                    outfit_damage={}
                )
            return new_state.world_snapshot[char_id]

        if isinstance(event, CharacterEnteredLocation):
            char_state = _get_or_create_character_state(event.character_id)
            char_state.location = event.location

        elif isinstance(event, CharacterChangedOutfit):
            char_state = _get_or_create_character_state(event.character_id)
            char_state.active_outfit_id = event.outfit_id

        elif isinstance(event, CharacterPickedUpObject):
            char_state = _get_or_create_character_state(event.character_id)
            if event.object_id not in char_state.held_objects:
                char_state.held_objects.append(event.object_id)
            if event.object_id not in new_state.object_states:
                new_state.object_states[event.object_id] = "intact"

        elif isinstance(event, CharacterDroppedObject):
            char_state = _get_or_create_character_state(event.character_id)
            if event.object_id not in char_state.held_objects:
                raise ValueError(f"Cannot drop object {event.object_id} because it is not held by {event.character_id}")
            char_state.held_objects.remove(event.object_id)

        elif isinstance(event, CharacterInjured):
            char_state = _get_or_create_character_state(event.character_id)
            if event.injury not in char_state.injuries:
                char_state.injuries.append(event.injury)

        elif isinstance(event, OutfitDamaged):
            char_state = _get_or_create_character_state(event.character_id)
            if char_state.active_outfit_id != event.outfit_id:
                raise ValueError(f"Cannot damage outfit {event.outfit_id} for {event.character_id} because they are wearing {char_state.active_outfit_id}")
            char_state.outfit_damage[event.region] = "torn"

        elif isinstance(event, ObjectBroken):
            if event.object_id not in new_state.object_states:
                raise ValueError(f"Cannot break object {event.object_id} because it does not exist in the continuity state")
            new_state.object_states[event.object_id] = "broken"

        elif isinstance(event, CharacterEmotionChanged):
            char_state = _get_or_create_character_state(event.character_id)
            char_state.emotion = event.emotion

        else:
            raise ValueError(f"Unsupported event type: {type(event)}")

        return new_state

    @staticmethod
    def replay(initial_state: ContinuityState, events: List[ContinuityEvent]) -> ContinuityState:
        current_state = initial_state
        # Sort events by sequence to ensure chronological replay
        sorted_events = sorted(events, key=lambda e: e.sequence)
        for event in sorted_events:
            current_state = ContinuityReducer.apply(current_state, event)
        return current_state
