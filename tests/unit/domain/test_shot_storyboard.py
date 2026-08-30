from datetime import datetime, timezone

import pytest

from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.value_objects.storyboard_frame import StoryboardFrame


def _frame(index: int = 0, contract_id: str = "shot-1") -> StoryboardFrame:
    return StoryboardFrame(
        id=f"frame-{index}",
        shot_contract_id=contract_id,
        sequence_index=index,
        media_asset_id=f"asset-{index}",
        storage_key=f"storyboards/shot-1/{index}.png",
        content_type="image/png",
        provider="fake:keyframe",
        provider_asset_id=f"provider-{index}",
        width=1024,
        height=1024,
        reference_asset_ids=("reference-1",),
        created_at=datetime.now(timezone.utc),
    )


def test_storyboard_adds_frames_in_sequence_and_round_trips():
    storyboard = ShotStoryboard.create("shot-1").with_frame(_frame(2)).with_frame(_frame(0))

    assert [frame.sequence_index for frame in storyboard.frames] == [0, 2]
    assert ShotStoryboard.from_dict(storyboard.to_dict()) == storyboard
    assert all(not frame.storage_key.startswith("C:") for frame in storyboard.frames)


def test_storyboard_rejects_duplicate_sequence_and_wrong_contract():
    storyboard = ShotStoryboard.create("shot-1").with_frame(_frame())
    with pytest.raises(ValueError, match="already contains"):
        storyboard.with_frame(_frame())
    with pytest.raises(ValueError, match="another shot"):
        storyboard.with_frame(_frame(1, "shot-2"))


def test_storyboard_frame_rejects_machine_specific_storage_path():
    frame_data = _frame().to_dict()
    frame_data["storage_key"] = "C:\\Users\\creator\\frame.png"
    with pytest.raises(ValueError, match="portable"):
        StoryboardFrame.from_dict(frame_data)
