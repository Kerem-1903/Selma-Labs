from dataclasses import dataclass
from typing import List, Dict, Any
from core.domain.value_objects.character_identity import ReferenceView

@dataclass(frozen=True)
class CharacterBibleValidationReport:
    missing_views: List[ReferenceView]
    invalid_references: List[str]
    is_complete: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "missing_views": [v.value for v in self.missing_views],
            "invalid_references": self.invalid_references,
            "is_complete": self.is_complete
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterBibleValidationReport":
        return cls(
            missing_views=[ReferenceView(v) for v in data.get("missing_views", [])],
            invalid_references=data.get("invalid_references", []),
            is_complete=data.get("is_complete", False)
        )
