from dataclasses import dataclass
from typing import Optional, List

# Re-use existing CharacterState if possible, or define here if strictly required
from core.domain.entities.character_state import CharacterState

@dataclass
class ShotPlan:
    id: str
    script_id: str
    scene_plan_id: str
    prompt: str
    duration_seconds: float
    character_state: CharacterState

@dataclass
class ShotMotionClip:
    video_path: str
    hash: str
    seed: int
    cached: bool
