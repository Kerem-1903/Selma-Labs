from unittest.mock import AsyncMock

import pytest

from core.application.services.rig_validation_service import RigValidationService
from core.domain.entities.character_rig import (
    AnimeShapeKeyEnum,
    RigSpecification,
    StandardPoseEnum,
)
from core.domain.ports.character_rig_port import CharacterRigPort, RigValidationReport


def _complete_specification(**overrides: object) -> RigSpecification:
    values = {
        "has_ik_arm_l": True,
        "has_ik_arm_r": True,
        "has_ik_leg_l": True,
        "has_ik_leg_r": True,
        "has_fk_arm_l": True,
        "has_fk_arm_r": True,
        "has_fk_leg_l": True,
        "has_fk_leg_r": True,
        "has_secondary_hair": True,
        "has_secondary_jacket": True,
        "shape_keys": frozenset(item.value for item in AnimeShapeKeyEnum),
        "available_actions": frozenset(item.value for item in StandardPoseEnum),
    }
    values.update(overrides)
    return RigSpecification(**values)


@pytest.mark.asyncio
async def test_validate_character_rig_success():
    port = AsyncMock(spec=CharacterRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=_complete_specification(),
        errors=(),
    )

    report = await RigValidationService(port).validate_character_rig("dummy.blend")

    assert report.is_valid is True
    assert report.errors == ()


@pytest.mark.asyncio
async def test_incomplete_rig_cannot_pass_without_walk_action():
    port = AsyncMock(spec=CharacterRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=_complete_specification(
            has_ik_leg_l=False,
            has_fk_arm_r=False,
            has_secondary_hair=False,
            available_actions=frozenset(),
        ),
        errors=(),
    )

    report = await RigValidationService(port).validate_character_rig("dummy.blend")

    assert report.is_valid is False
    assert "IK_LEG_L" in report.errors[0]
    assert "FK_ARM_R" in report.errors[0]
    assert "SECONDARY_HAIR" in report.errors[0]
    assert "WALK_2STEP" in report.errors[-1]


@pytest.mark.asyncio
async def test_missing_expression_shape_keys_are_reported():
    port = AsyncMock(spec=CharacterRigPort)
    mouth_only = frozenset(
        {
            AnimeShapeKeyEnum.MOUTH_A.value,
            AnimeShapeKeyEnum.MOUTH_E.value,
            AnimeShapeKeyEnum.MOUTH_I.value,
            AnimeShapeKeyEnum.MOUTH_O.value,
            AnimeShapeKeyEnum.MOUTH_U.value,
            AnimeShapeKeyEnum.MOUTH_CLOSED.value,
        }
    )
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=_complete_specification(shape_keys=mouth_only),
        errors=(),
    )

    report = await RigValidationService(port).validate_character_rig("dummy.blend")

    assert report.is_valid is False
    assert "EYE_BLINK_L" in report.errors[0]
    assert "BROW_ANGRY" in report.errors[0]


@pytest.mark.asyncio
async def test_adapter_errors_are_preserved_with_domain_errors():
    port = AsyncMock(spec=CharacterRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=False,
        specification=_complete_specification(has_secondary_jacket=False),
        errors=("Multiple armatures found.",),
    )

    report = await RigValidationService(port).validate_character_rig("dummy.blend")

    assert report.is_valid is False
    assert report.errors[0] == "Multiple armatures found."
    assert "SECONDARY_JACKET" in report.errors[1]
