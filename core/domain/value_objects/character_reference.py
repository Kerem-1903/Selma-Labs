from dataclasses import dataclass
from typing import Dict, Any
from .character_identity import ReferenceView

@dataclass(frozen=True)
class CharacterReference:
    id: str
    character_id: str
    view: ReferenceView
    asset_id: str
    revision: int = 1
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "view": self.view.value,
            "asset_id": self.asset_id,
            "revision": self.revision,
            "content_hash": self.content_hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterReference":
        return cls(
            id=data["id"],
            character_id=data["character_id"],
            view=ReferenceView(data["view"]),
            asset_id=data["asset_id"],
            revision=data.get("revision", 1),
            content_hash=data.get("content_hash", "")
        )
