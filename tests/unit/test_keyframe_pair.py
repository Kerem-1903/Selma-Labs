import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from core.application.services.keyframe_generation_service import (
    KeyframeGenerationService,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.keyframe import KeyframePair
from core.domain.entities.shot_animation import AnimationShotPlan
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _generated_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (256, 256), "white").save(buffer, format="PNG")
    return buffer.getvalue()


GENERATED_PNG_BYTES = _generated_png()

@pytest.mark.asyncio
async def test_generate_keyframe_pair_calls_provider_twice(tmp_path):
    generator = AsyncMock()
    generator.generate_keyframe.side_effect = [
        GeneratedKeyframe(image_bytes=GENERATED_PNG_BYTES, content_type="image/png", width=256, height=256),
        GeneratedKeyframe(image_bytes=GENERATED_PNG_BYTES, content_type="image/png", width=256, height=256)
    ]

    bibles_repo = AsyncMock()
    bibles_repo.load.return_value = "dummy_bible"

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
    approval_guard = AsyncMock(return_value=object())
    service = KeyframeGenerationService(
        generator=generator,
        storage=storage,
        character_bibles=bibles_repo,
        storyboards=AsyncMock(),
        human_review_required=False,
        conditioning_builder=builder,
        view_pack_approval_guard=approval_guard,
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
    assert pair.start_keyframe.image_bytes == GENERATED_PNG_BYTES
    assert pair.end_keyframe.image_bytes == GENERATED_PNG_BYTES
    assert await storage.exists(pair.start_storage_key)
    assert await storage.exists(pair.end_storage_key)
    assert pair.human_approved is False
    approval_guard.assert_awaited_once_with("akira", 1)

    assert generator.generate_keyframe.call_count == 2
    requests = [call.args[0] for call in generator.generate_keyframe.call_args_list]
    assert requests[0].visual_constraints["pose_storage_key"] == "poses/start.png"
    assert requests[1].visual_constraints["pose_storage_key"] == "poses/end.png"
    assert all(
        request.visual_constraints["latent_mode"] == "empty" for request in requests
    )
    assert all(
        "full body" in request.visual_constraints["extra_tags"]
        for request in requests
    )
    assert all(
        request.visual_constraints["identity_strength"] == 0.75
        for request in requests
    )
    assert all(
        request.visual_constraints["identity_end_at"] == 0.72
        for request in requests
    )
    assert all("face mask" in request.negative_prompts for request in requests)
    assert all("gun" in request.negative_prompts for request in requests)


@pytest.mark.asyncio
async def test_lora_primary_pair_uses_moderate_visual_identity_strength(tmp_path):
    generator = AsyncMock()
    generator.generate_keyframe.return_value = GeneratedKeyframe(
        image_bytes=GENERATED_PNG_BYTES,
        content_type="image/png",
        width=256,
        height=256,
    )
    storage = LocalFsStorage(str(tmp_path))
    await storage.save("poses/start.png", PNG_BYTES, "image/png")
    await storage.save("poses/end.png", PNG_BYTES, "image/png")
    character_bibles = AsyncMock()
    character_bibles.load.return_value = CharacterBible.akira()
    builder = MagicMock()
    builder.build.return_value = KeyframeGenerationRequest(
        shot_contract_id="shot-lora",
        camera_constraints={},
        action_constraints={},
        visual_constraints={},
        character_conditioning=(),
        reference_asset_ids=(),
        reference_storage_keys=(),
        negative_prompts=(),
        width=1024,
        height=1024,
    )
    service = KeyframeGenerationService(
        generator=generator,
        storage=storage,
        character_bibles=character_bibles,
        storyboards=AsyncMock(),
        human_review_required=False,
        conditioning_builder=builder,
        character_lora_active=True,
        view_pack_approval_guard=AsyncMock(return_value=object()),
    )

    shot_plan = AnimationShotPlan(
        id="shot-lora",
        script_id="script1",
        scene_plan_id="scene1",
        prompt="akira ready stance",
        prompt_end="akira raises katana",
        duration_seconds=2.0,
        character_state=CharacterState(
            character_id="akira",
            active_outfit_id="akira-default",
            injuries=[],
            held_objects=["katana"],
        ),
        start_pose_reference_key="poses/start.png",
        end_pose_reference_key="poses/end.png",
        controlnet_type="openpose",
    )

    await service.generate_keyframe_pair(shot_plan)

    requests = [call.args[0] for call in generator.generate_keyframe.call_args_list]
    assert len(requests) == 2
    assert all(
        request.visual_constraints["identity_strength"] == 0.5
        for request in requests
    )
