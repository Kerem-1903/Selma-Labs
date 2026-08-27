from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass(frozen=True)
class Outfit:
    id: str
    character_id: str
    description: str
    reference_image_keys: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "description": self.description,
            "reference_image_keys": self.reference_image_keys,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Outfit":
        return cls(
            id=data["id"],
            character_id=data["character_id"],
            description=data["description"],
            reference_image_keys=data.get("reference_image_keys", []),
        )
