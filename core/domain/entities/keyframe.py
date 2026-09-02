from dataclasses import dataclass
from pathlib import PurePosixPath

from core.domain.value_objects.generated_keyframe import GeneratedKeyframe

@dataclass(frozen=True)
class KeyframePair:
    """Unapproved start/end candidates with durable provider-neutral keys."""

    start_keyframe: GeneratedKeyframe
    end_keyframe: GeneratedKeyframe
    start_storage_key: str
    end_storage_key: str
    human_approved: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("start_storage_key", self.start_storage_key),
            ("end_storage_key", self.end_storage_key),
        ):
            path = PurePosixPath(value.replace("\\", "/"))
            if not value.strip() or path.is_absolute() or ".." in path.parts or ":" in value:
                raise ValueError(f"{name} must be a portable relative storage key.")
        if self.human_approved:
            raise ValueError("Generated keyframe pairs must begin unapproved.")
