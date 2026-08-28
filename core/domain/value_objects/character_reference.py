from dataclasses import dataclass
from typing import Dict, Any
from .character_identity import ReferenceView

@dataclass(frozen=True)
class CharacterReference:
    id: str
    character_id: str
    view: ReferenceView
    asset_id: str
    storage_key: str = ""
    content_type: str = ""
    content_hash: str = ""
    revision: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "view": self.view.value,
            "asset_id": self.asset_id,
            "storage_key": self.storage_key,
            "content_type": self.content_type,
            "content_hash": self.content_hash,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterReference":
        return cls(
            id=data["id"],
            character_id=data["character_id"],
            view=ReferenceView(data["view"]),
            asset_id=data["asset_id"],
            storage_key=data.get("storage_key", ""),
            content_type=data.get("content_type", ""),
            content_hash=data.get("content_hash", ""),
            revision=int(data.get("revision", 1)),
        )
