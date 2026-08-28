from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass(frozen=True)
class StyleProfile:
    base_style: str
    lighting_preferences: List[str] = field(default_factory=list)
    color_palette: List[str] = field(default_factory=list)
    negative_prompts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_style": self.base_style,
            "lighting_preferences": self.lighting_preferences,
            "color_palette": self.color_palette,
            "negative_prompts": self.negative_prompts
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StyleProfile":
        return cls(
            base_style=data.get("base_style", ""),
            lighting_preferences=data.get("lighting_preferences", []),
            color_palette=data.get("color_palette", []),
            negative_prompts=data.get("negative_prompts", [])
        )
