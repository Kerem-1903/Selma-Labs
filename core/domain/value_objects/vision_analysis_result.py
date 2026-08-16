from dataclasses import dataclass, field
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
    text_present: bool = False
    logo_present: bool = False
    dominant_subject: str = ""
    observed_subjects: List[str] = field(default_factory=list)
    observed_actions: List[str] = field(default_factory=list)
    observed_relations: List[str] = field(default_factory=list)
    subject_pose: str = ""
    camera_angle: str = ""
    background_signature: str = ""
    motion_energy: float | None = None

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
            "text_present": self.text_present,
            "logo_present": self.logo_present,
            "dominant_subject": self.dominant_subject,
            "observed_subjects": list(self.observed_subjects),
            "observed_actions": list(self.observed_actions),
            "observed_relations": list(self.observed_relations),
            "subject_pose": self.subject_pose,
            "camera_angle": self.camera_angle,
            "background_signature": self.background_signature,
            "motion_energy": self.motion_energy,
        }
