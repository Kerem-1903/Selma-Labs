from dataclasses import dataclass, field
from typing import List, Dict, Any
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.outfit import Outfit
from core.domain.value_objects.style_profile import StyleProfile

@dataclass
class CharacterBible:
    character_id: str
    identity_constraints: IdentityConstraints
    style_profile: StyleProfile
    reference_pack: Dict[ReferenceView, CharacterReference] = field(default_factory=dict)
    outfit_catalog: List[Outfit] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_id": self.character_id,
            "identity_constraints": self.identity_constraints.to_dict(),
            "style_profile": self.style_profile.to_dict(),
            "reference_pack": {
                view.value: ref.to_dict()
                for view, ref in self.reference_pack.items()
            },
            "outfit_catalog": [outfit.to_dict() for outfit in self.outfit_catalog]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterBible":
        refs = {
            ReferenceView(view_str): CharacterReference.from_dict(ref_data)
            for view_str, ref_data in data.get("reference_pack", {}).items()
        }
        outfits = [
            Outfit.from_dict(o_data)
            for o_data in data.get("outfit_catalog", [])
        ]
        return cls(
            character_id=data["character_id"],
            identity_constraints=IdentityConstraints.from_dict(data.get("identity_constraints", {})),
            style_profile=StyleProfile.from_dict(data.get("style_profile", {})),
            reference_pack=refs,
            outfit_catalog=outfits
        )
