from dataclasses import dataclass
from typing import Dict, Any
from .character_identity import ReferenceView

@dataclass(frozen=True)
class CharacterReference:
    id: str
    character_id: str
    view: ReferenceView
    asset_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "view": self.view.value,
            "asset_id": self.asset_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterReference":
        return cls(
            id=data["id"],
            character_id=data["character_id"],
            view=ReferenceView(data["view"]),
            asset_id=data["asset_id"]
        )
