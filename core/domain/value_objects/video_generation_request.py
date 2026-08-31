from dataclasses import dataclass, field
from typing import List, Dict, Any
from core.domain.value_objects.render_profile import RenderProfile

@dataclass(frozen=True)
class VideoGenerationRequest:
    shot_contract_id: str
    target_duration_seconds: float
    reference_image_keys: List[str] = field(default_factory=list)
    generation_constraints: Dict[str, Any] = field(default_factory=dict)
    render_profile: RenderProfile = RenderProfile.BALANCED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_contract_id": self.shot_contract_id,
            "target_duration_seconds": self.target_duration_seconds,
            "reference_image_keys": self.reference_image_keys,
            "generation_constraints": self.generation_constraints,
            "render_profile": self.render_profile.value
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoGenerationRequest":
        return cls(
            shot_contract_id=data["shot_contract_id"],
            target_duration_seconds=data["target_duration_seconds"],
            reference_image_keys=data.get("reference_image_keys", []),
            generation_constraints=data.get("generation_constraints", {}),
            render_profile=RenderProfile(data.get("render_profile", RenderProfile.BALANCED.value))
        )
