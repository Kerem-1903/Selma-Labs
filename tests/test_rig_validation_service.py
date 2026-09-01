import pytest
from unittest.mock import AsyncMock

from core.application.services.rig_validation_service import RigValidationService
from core.domain.entities.character_rig import RigSpecification, AnimeShapeKeyEnum
from core.domain.ports.blender_rig_port import BlenderRigPort, RigValidationReport

@pytest.mark.asyncio
async def test_validate_character_rig_success():
    port = AsyncMock(spec=BlenderRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=RigSpecification(
            has_ik_arm_l=True,
            has_ik_arm_r=True,
            has_ik_leg_l=True,
            has_ik_leg_r=True,
            has_fk_arm_l=True,
            has_fk_arm_r=True,
            has_fk_leg_l=True,
            has_fk_leg_r=True,
            has_secondary_hair=True,
            has_secondary_jacket=True,
            shape_keys=frozenset([
                AnimeShapeKeyEnum.MOUTH_A.value,
                AnimeShapeKeyEnum.MOUTH_E.value,
                AnimeShapeKeyEnum.MOUTH_I.value,
                AnimeShapeKeyEnum.MOUTH_O.value,
                AnimeShapeKeyEnum.MOUTH_U.value,
                AnimeShapeKeyEnum.MOUTH_CLOSED.value,
            ])
        ),
        errors=[]
    )

    service = RigValidationService(port)
    report = await service.validate_character_rig("dummy_path")

    assert report.is_valid is True
    assert len(report.errors) == 0

@pytest.mark.asyncio
async def test_validate_character_rig_missing_lipsync():
    port = AsyncMock(spec=BlenderRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=RigSpecification(
            has_ik_arm_l=True,
            has_ik_arm_r=True,
            has_ik_leg_l=True,
            has_ik_leg_r=True,
            has_fk_arm_l=True,
            has_fk_arm_r=True,
            has_fk_leg_l=True,
            has_fk_leg_r=True,
            has_secondary_hair=True,
            has_secondary_jacket=True,
            shape_keys=frozenset([])  # Missing lipsync shape keys
        ),
        errors=[]
    )

    service = RigValidationService(port)
    report = await service.validate_character_rig("dummy_path")

    assert report.is_valid is False
    assert "Rig is missing required shape keys for lipsync." in report.errors

@pytest.mark.asyncio
async def test_validate_character_rig_missing_ik_legs_for_locomotion():
    port = AsyncMock(spec=BlenderRigPort)
    port.validate_rig.return_value = RigValidationReport(
        is_valid=True,
        specification=RigSpecification(
            has_ik_arm_l=True,
            has_ik_arm_r=True,
            has_ik_leg_l=False,  # Missing IK legs
            has_ik_leg_r=False,
            has_fk_arm_l=True,
            has_fk_arm_r=True,
            has_fk_leg_l=True,
            has_fk_leg_r=True,
            has_secondary_hair=True,
            has_secondary_jacket=True,
            shape_keys=frozenset([
                AnimeShapeKeyEnum.MOUTH_A.value,
                AnimeShapeKeyEnum.MOUTH_E.value,
                AnimeShapeKeyEnum.MOUTH_I.value,
                AnimeShapeKeyEnum.MOUTH_O.value,
                AnimeShapeKeyEnum.MOUTH_U.value,
                AnimeShapeKeyEnum.MOUTH_CLOSED.value,
            ]),
            available_actions=frozenset(["walk_2step"])
        ),
        errors=[]
    )

    service = RigValidationService(port)
    report = await service.validate_character_rig("dummy_path")

    assert report.is_valid is False
    assert "Rig is missing IK legs, which are required to prevent foot sliding during locomotion actions." in report.errors
