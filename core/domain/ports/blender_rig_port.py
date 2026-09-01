from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.domain.entities.character_rig import RigSpecification


@dataclass(frozen=True)
class RigValidationReport:
    is_valid: bool
    specification: RigSpecification
    errors: list[str]


class BlenderRigPort(ABC):
    @abstractmethod
    async def validate_rig(self, model_path: str) -> RigValidationReport:
        """
        Validates the given Blender model rig against the RigSpecification.
        """
        pass

    @abstractmethod
    async def bake_action_preview(self, model_path: str, action_name: str, output_path: str, fps: int = 24) -> str:
        """
        Bakes/renders a preview of a specific action from the rig to the output path.
        Returns the path to the rendered output.
        """
        pass
