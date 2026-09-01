"""Backward-compatible imports for the engine-neutral character rig port."""

from core.domain.ports.character_rig_port import CharacterRigPort, RigValidationReport

BlenderRigPort = CharacterRigPort

__all__ = ["BlenderRigPort", "RigValidationReport"]
