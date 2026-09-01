from core.domain.ports.character_rig_port import CharacterRigPort, RigValidationReport


class RigValidationService:
    def __init__(self, character_rig_port: CharacterRigPort) -> None:
        self.character_rig_port = character_rig_port

    async def validate_character_rig(self, model_path: str) -> RigValidationReport:
        """Validate the complete A9 rig and acting contract."""
        report = await self.character_rig_port.validate_rig(model_path)
        errors = list(report.errors)
        specification = report.specification

        missing_controls = specification.missing_a9_controls()
        if missing_controls:
            errors.append(
                f"Rig is missing required A9 controls: {', '.join(missing_controls)}."
            )

        missing_shape_keys = specification.missing_a9_shape_keys()
        if missing_shape_keys:
            errors.append(
                "Rig is missing required A9 shape keys: "
                f"{', '.join(missing_shape_keys)}."
            )

        missing_actions = specification.missing_a9_actions()
        if missing_actions:
            errors.append(
                f"Rig is missing required A9 actions: {', '.join(missing_actions)}."
            )

        unique_errors = tuple(dict.fromkeys(errors))
        return RigValidationReport(
            is_valid=report.is_valid and not unique_errors,
            specification=specification,
            errors=unique_errors,
        )
