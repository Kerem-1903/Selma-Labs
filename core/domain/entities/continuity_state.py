from dataclasses import dataclass, field
from typing import Any

from .character_state import CharacterState


@dataclass
class ContinuityState:
    id: str
    world_snapshot: dict[str, CharacterState] = field(default_factory=dict)
    object_states: dict[str, str] = field(default_factory=dict)

    def update_character(self, state: CharacterState) -> None:
        self.world_snapshot[state.character_id] = state

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "world_snapshot": {
                char_id: state.to_dict()
                for char_id, state in self.world_snapshot.items()
            },
            "object_states": self.object_states
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityState":
        snapshot = {
            char_id: CharacterState.from_dict(state_data)
            for char_id, state_data in data.get("world_snapshot", {}).items()
        }
        return cls(
            id=data["id"],
            world_snapshot=snapshot,
            object_states=data.get("object_states", {})
        )
