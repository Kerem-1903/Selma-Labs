from core.domain.ports.blender_rig_port import BlenderRigPort, RigValidationReport


class RigValidationService:
    def __init__(self, blender_rig_port: BlenderRigPort) -> None:
        self.blender_rig_port = blender_rig_port

    async def validate_character_rig(self, model_path: str) -> RigValidationReport:
        """
        Orchestrates model file checks and verifies mandatory anime shape keys
        and rig configurations via the BlenderRigPort.
        """
        # Here we could add additional business logic, file existence checks, etc.
        report = await self.blender_rig_port.validate_rig(model_path)

        # We can also add more domain specific rules. For example, if lipsync is required:
        errors = list(report.errors)
        is_valid = report.is_valid

        if is_valid and not report.specification.is_lipsync_ready():
            errors.append("Rig is missing required shape keys for lipsync.")
            is_valid = False

        # Example logic for preventing foot sliding during locomotion
        # We ensure IK legs are present for walk actions to prevent foot sliding
        has_walk = any("walk" in action.lower() for action in report.specification.available_actions)
        has_ik_legs = report.specification.has_ik_leg_l and report.specification.has_ik_leg_r

        if is_valid and has_walk and not has_ik_legs:
            errors.append("Rig is missing IK legs, which are required to prevent foot sliding during locomotion actions.")
            is_valid = False

        if not is_valid:
            return RigValidationReport(
                is_valid=False,
                specification=report.specification,
                errors=errors
            )

        return report
