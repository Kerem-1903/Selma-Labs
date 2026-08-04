from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class VisionAnalysisResult:
    relevance_score: float
    scene_type: str
    lighting: str
    dominant_colors: List[str]
    indoors: bool
    outdoors: bool
    camera_motion: str
    people_present: bool
    vehicles_present: bool
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevance_score": self.relevance_score,
            "scene_type": self.scene_type,
            "lighting": self.lighting,
            "dominant_colors": self.dominant_colors,
            "indoors": self.indoors,
            "outdoors": self.outdoors,
            "camera_motion": self.camera_motion,
            "people_present": self.people_present,
            "vehicles_present": self.vehicles_present,
            "confidence": self.confidence,
        }
