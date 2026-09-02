import pytest
import base64
from unittest.mock import AsyncMock
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.domain.entities.shot_animation import AnimationShotPlan
from core.domain.entities.character_state import CharacterState
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from core.domain.entities.keyframe import KeyframePair
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from infrastructure.storage.local_fs_storage import LocalFsStorage

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

@pytest.mark.asyncio
async def test_generate_keyframe_pair_calls_provider_twice(tmp_path):
    generator = AsyncMock()
    generator.generate_keyframe.side_effect = [
        GeneratedKeyframe(image_bytes=PNG_BYTES, content_type="image/png", width=1024, height=1024),
        GeneratedKeyframe(image_bytes=PNG_BYTES, content_type="image/png", width=1024, height=1024)
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


    storage = LocalFsStorage(str(tmp_path))
    await storage.save("poses/start.png", PNG_BYTES, "image/png")
    await storage.save("poses/end.png", PNG_BYTES, "image/png")
    service = KeyframeGenerationService(
        generator=generator,
        storage=storage,
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
            prompt_end="prompt end",
        duration_seconds=2.0,
        character_state=CharacterState(character_id="akira", active_outfit_id="casual", injuries=[], held_objects=[]),
        start_pose_reference_key="poses/start.png",
        end_pose_reference_key="poses/end.png",
        controlnet_type="openpose"
    )

    pair = await service.generate_keyframe_pair(shot_plan)

    assert isinstance(pair, KeyframePair)
    assert pair.start_keyframe.image_bytes == PNG_BYTES
    assert pair.end_keyframe.image_bytes == PNG_BYTES
    assert await storage.exists(pair.start_storage_key)
    assert await storage.exists(pair.end_storage_key)
    assert pair.human_approved is False

    assert generator.generate_keyframe.call_count == 2
    requests = [call.args[0] for call in generator.generate_keyframe.call_args_list]
    assert requests[0].visual_constraints["pose_storage_key"] == "poses/start.png"
    assert requests[1].visual_constraints["pose_storage_key"] == "poses/end.png"
