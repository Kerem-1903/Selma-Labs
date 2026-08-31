from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.application.services.approved_keyframe_motion_service import (
    ApprovedKeyframeMotionService,
)
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import MotionGenerationError, StorageError
from core.domain.value_objects.generated_video_clip import GeneratedVideoClip
from core.domain.value_objects.storyboard_frame import StoryboardFrame
from infrastructure.providers.video.fake_image_to_video_provider import (
    FakeImageToVideoProvider,
)
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.repositories.local_json_shot_motion_clip_repository import (
    LocalJsonShotMotionClipRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


async def _setup(tmp_path, *, provider=None, commit_candidate=True):
    storage = LocalFsStorage(str(tmp_path / "assets"))
    source_key = "storyboards/shot-a8/frames/0000-approved.png"
    await storage.save(source_key, b"\x89PNG\r\n\x1a\nsource", "image/png")
    evaluation = CandidateEvaluationService(
        SqliteKeyframeCandidateRepository(":memory:")
    )
    candidate = await evaluation.register_candidate("shot-a8", source_key, {})
    await evaluation.approve_candidate(candidate.id)
    if commit_candidate:
        await evaluation.mark_candidate_committed(candidate.id)
    frame = StoryboardFrame(
        id="frame-approved",
        shot_contract_id="shot-a8",
        sequence_index=0,
        media_asset_id="media-approved",
        storage_key=source_key,
        content_type="image/png",
        provider="fake:keyframe",
        provider_asset_id="provider-image",
        width=1024,
        height=1024,
        reference_asset_ids=("akira-front",),
        created_at=datetime.now(timezone.utc),
    )
    storyboard = ShotStoryboard.create("shot-a8").with_frame(frame)
    clip_repository = LocalJsonShotMotionClipRepository(tmp_path / "clips")
    generator = provider or FakeImageToVideoProvider()
    service = ApprovedKeyframeMotionService(
        generator=generator,
        storage=storage,
        candidates=evaluation,
        clips=clip_repository,
    )
    return service, generator, storage, clip_repository, storyboard, candidate


@pytest.mark.asyncio
async def test_committed_keyframe_becomes_storage_backed_motion_clip(tmp_path):
    service, generator, storage, repository, storyboard, candidate = await _setup(
        tmp_path
    )

    clip = await service.generate(
        storyboard=storyboard,
        target_duration_seconds=4.0,
        motion_prompt="Akira draws her katana",
        camera_motion="slow push-in",
        width=1280,
        height=720,
        fps=24,
        seed=1903,
    )

    assert clip.candidate_id == candidate.id
    assert clip.source_image_storage_key == storyboard.frames[0].storage_key
    assert clip.storage_key.endswith(".mp4")
    assert await storage.exists(clip.storage_key)
    assert (await storage.load(clip.storage_key))[4:8] == b"ftyp"
    assert await repository.load(clip.id) == clip
    assert generator.requests[0].source_image_storage_key == clip.source_image_storage_key
    assert generator.requests[0].motion_prompt == "Akira draws her katana"


@pytest.mark.asyncio
async def test_uncommitted_candidate_cannot_reach_video_provider(tmp_path):
    service, generator, _, _, storyboard, _ = await _setup(
        tmp_path, commit_candidate=False
    )

    with pytest.raises(MotionGenerationError, match="committed"):
        await service.generate(
            storyboard=storyboard,
            target_duration_seconds=4,
            motion_prompt="walk",
        )
    assert generator.requests == []


@pytest.mark.asyncio
async def test_missing_committed_image_is_controlled_error(tmp_path):
    service, generator, storage, _, storyboard, _ = await _setup(tmp_path)
    storage.delete_file(storyboard.frames[0].storage_key)

    with pytest.raises(StorageError, match="was not found"):
        await service.generate(
            storyboard=storyboard,
            target_duration_seconds=4,
            motion_prompt="walk",
        )
    assert generator.requests == []


class InvalidVideoProvider(FakeImageToVideoProvider):
    async def generate_video(self, request):
        self.requests.append(request)
        return GeneratedVideoClip(
            video_bytes=b"not-an-mp4",
            content_type="video/mp4",
            width=1024,
            height=576,
            duration_seconds=4,
            fps=24,
            provider_asset_id="invalid",
        )


@pytest.mark.asyncio
async def test_invalid_provider_bytes_are_not_persisted(tmp_path):
    provider = InvalidVideoProvider()
    service, _, storage, _, storyboard, _ = await _setup(
        tmp_path, provider=provider
    )

    with pytest.raises(MotionGenerationError, match="do not match"):
        await service.generate(
            storyboard=storyboard,
            target_duration_seconds=4,
            motion_prompt="walk",
        )
    assert not list((tmp_path / "assets" / "motion").rglob("*.mp4"))
