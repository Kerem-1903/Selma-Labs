import pytest

from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


def test_keyframe_request_round_trips_typed_constraints():
    request = KeyframeGenerationRequest(
        shot_contract_id="shot-1",
        camera_constraints={"angle": "low-angle"},
        action_constraints={"primary_action": "draw sword"},
        visual_constraints={"lighting": "low-key"},
        character_conditioning=({"character_id": "akira"},),
        reference_asset_ids=("asset-1",),
        reference_storage_keys=("characters/akira/front.png",),
        negative_prompts=("identity drift",),
        width=1280,
        height=720,
        seed=42,
    )

    restored = KeyframeGenerationRequest.from_dict(request.to_dict())

    assert restored == request
    assert "prompt" not in request.to_dict()


def test_keyframe_request_rejects_misaligned_references():
    with pytest.raises(ValueError, match="stay aligned"):
        KeyframeGenerationRequest(
            shot_contract_id="shot-1",
            camera_constraints={},
            action_constraints={},
            visual_constraints={},
            reference_asset_ids=("asset-1",),
        )
