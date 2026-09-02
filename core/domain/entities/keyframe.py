from dataclasses import dataclass

from core.domain.value_objects.generated_keyframe import GeneratedKeyframe

@dataclass(frozen=True)
class KeyframePair:
    """Holds a generated start and end keyframe for a dual keyframing workflow."""

    start_keyframe: GeneratedKeyframe
    end_keyframe: GeneratedKeyframe
