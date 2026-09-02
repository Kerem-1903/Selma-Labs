import pytest
from unittest.mock import AsyncMock
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.domain.entities.shot_animation import AnimationShotPlan
from core.domain.entities.character_state import CharacterState
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from core.domain.entities.keyframe import KeyframePair
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe

@pytest.mark.asyncio
async def test_generate_keyframe_pair_calls_provider_twice():
    generator = AsyncMock()
    generator.generate_keyframe.side_effect = [
        GeneratedKeyframe(image_bytes=b"start", content_type="image/png", width=1024, height=1024),
        GeneratedKeyframe(image_bytes=b"end", content_type="image/png", width=1024, height=1024)
    ]

    bibles_repo = AsyncMock()
    bibles_repo.load.return_value = "dummy_bible"

    from unittest.mock import MagicMock
    builder = MagicMock()
    req_dummy = KeyframeGenerationRequest(
        shot_contract_id="dummy",
        camera_constraints={},
        action_constraints={},
        visual_constraints={},
        character_conditioning=(),
        reference_asset_ids=(),
        reference_storage_keys=(),
        negative_prompts=(),
        width=1024,
        height=1024
    )
    builder.build.side_effect = [req_dummy, req_dummy]


    service = KeyframeGenerationService(
        generator=generator,
        storage=AsyncMock(),
        character_bibles=bibles_repo,
        storyboards=AsyncMock(),
        human_review_required=False,
        conditioning_builder=builder
    )

    shot_plan = AnimationShotPlan(
        id="shot1",
        script_id="script1",
        scene_plan_id="scene1",
        prompt="prompt",
        duration_seconds=2.0,
        character_state=CharacterState(character_id="akira", active_outfit_id="casual", injuries=[], held_objects=[]),
        start_keyframe_key="start_kf.png",
        end_keyframe_key="end_kf.png",
        pose_reference_key="pose.png",
        controlnet_type="openpose"
    )

    pair = await service.generate_keyframe_pair(shot_plan)

    assert isinstance(pair, KeyframePair)
    assert pair.start_keyframe.image_bytes == b"start"
    assert pair.end_keyframe.image_bytes == b"end"

    assert generator.generate_keyframe.call_count == 2
