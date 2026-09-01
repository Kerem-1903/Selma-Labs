from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.domain.entities.character_rig import RigSpecification


@dataclass(frozen=True)
class RigValidationReport:
    is_valid: bool
    specification: RigSpecification
    errors: tuple[str, ...]


class CharacterRigPort(ABC):
    """Engine-neutral boundary for inspecting rigs and rendering previews."""

    @abstractmethod
    async def validate_rig(self, model_path: str) -> RigValidationReport:
        raise NotImplementedError

    @abstractmethod
    async def bake_action_preview(
        self,
        model_path: str,
        action_name: str,
        output_path: str,
        fps: int = 24,
    ) -> str:
        raise NotImplementedError
