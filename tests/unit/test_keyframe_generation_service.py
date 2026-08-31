from __future__ import annotations

import pytest

from core.application.services.character_reference_asset_service import (
    CharacterReferenceAssetService,
)
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_contract import ShotContract
from core.domain.exceptions import KeyframeGenerationError
from core.domain.exceptions import StorageError
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.repositories.local_json_shot_storyboard_repository import (
    LocalJsonShotStoryboardRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _contract() -> ShotContract:
    return ShotContract(
        id="shot-a5-001",
        camera_constraints=CameraConstraints("eye-level", "35mm", "dolly"),
        action_constraints=ActionConstraints("raise katana"),
        visual_constraints=VisualConstraints("low-key", "neon street", "rain"),
        required_character_states=[
            CharacterState("akira", "battle-jacket", ["shoulder wound"], ["katana"])
        ],
    )


async def _service(tmp_path, generator=None):
    storage = LocalFsStorage(str(tmp_path / "assets"))
    bible_repository = LocalJsonCharacterBibleRepository(tmp_path / "bibles")
    storyboard_repository = LocalJsonShotStoryboardRepository(tmp_path / "storyboards")
    bible = CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints(
            "brown", "black", "angular", "athletic", "tall"
        ),
        style_profile=StyleProfile("anime", negative_prompts=["identity drift"]),
    )
    references = CharacterReferenceAssetService(storage)
    for view in (ReferenceView.FRONT, ReferenceView.PROFILE_LEFT, ReferenceView.FACE_CLOSEUP):
        await references.save_reference(bible, view, f"image-{view.value}".encode(), "image/png")
    await bible_repository.save(bible)
    return (
        KeyframeGenerationService(
            generator=generator or FakeKeyframeGenerationProvider(),
            storage=storage,
            character_bibles=bible_repository,
            storyboards=storyboard_repository,
            human_review_required=False,
        ),
        storage,
        storyboard_repository,
    )


def test_human_review_is_required_by_default(tmp_path):
    with pytest.raises(ValueError, match="Candidate evaluation service is required"):
        KeyframeGenerationService(
            generator=FakeKeyframeGenerationProvider(),
            storage=LocalFsStorage(str(tmp_path / "assets")),
            character_bibles=LocalJsonCharacterBibleRepository(tmp_path / "bibles"),
            storyboards=LocalJsonShotStoryboardRepository(tmp_path / "storyboards"),
        )


@pytest.mark.asyncio
async def test_akira_keyframe_generation_is_storage_backed_and_round_trips(tmp_path):
    service, storage, repository = await _service(tmp_path)

    storyboard = await service.generate(
        shot_contract=_contract(), width=1280, height=720, seed=1903
    )

    assert len(storyboard.frames) == 1
    frame = storyboard.frames[0]
    assert frame.provider == "fake:keyframe"
    assert frame.width == 1280
    assert frame.height == 720
    assert len(frame.reference_asset_ids) == 3
    assert await storage.exists(frame.storage_key)
    assert (await storage.load(frame.storage_key)).startswith(b"\x89PNG")
    assert await repository.load(storyboard.id) == storyboard
    persisted = (tmp_path / "storyboards" / f"{storyboard.id}.json").read_text("utf-8")
    assert str(tmp_path) not in persisted


class InvalidImageProvider(FakeKeyframeGenerationProvider):
    async def generate_keyframe(self, request):
        del request
        return GeneratedKeyframe(b"not-png", "image/png", 100, 100)


class SingleReferenceProvider(FakeKeyframeGenerationProvider):
    async def generate_keyframe(self, request):
        generated = await super().generate_keyframe(request)
        return GeneratedKeyframe(
            image_bytes=generated.image_bytes,
            content_type=generated.content_type,
            width=generated.width,
            height=generated.height,
            provider_asset_id=generated.provider_asset_id,
            metadata={"reference_asset_ids": [request.reference_asset_ids[0]]},
        )


@pytest.mark.asyncio
async def test_service_rejects_provider_bytes_that_do_not_match_content_type(tmp_path):
    service, _, _ = await _service(tmp_path, InvalidImageProvider())

    with pytest.raises(KeyframeGenerationError, match="do not match"):
        await service.generate(shot_contract=_contract())


@pytest.mark.asyncio
async def test_storyboard_records_only_references_used_by_provider(tmp_path):
    provider = SingleReferenceProvider()
    service, _, _ = await _service(tmp_path, provider)

    storyboard = await service.generate(shot_contract=_contract())

    assert storyboard.frames[0].reference_asset_ids == (
        provider.requests[0].reference_asset_ids[0],
    )


@pytest.mark.asyncio
async def test_service_reports_missing_reference_asset_before_generation(tmp_path):
    generator = FakeKeyframeGenerationProvider()
    service, storage, _ = await _service(tmp_path, generator)
    reference_key = next((tmp_path / "assets").rglob("*.png")).relative_to(
        tmp_path / "assets"
    ).as_posix()
    storage.delete_file(reference_key)

    with pytest.raises(StorageError, match="was not found"):
        await service.generate(shot_contract=_contract())
    assert generator.requests == []


@pytest.mark.asyncio
async def test_duplicate_sequence_is_rejected_before_creating_an_orphan_asset(tmp_path):
    generator = FakeKeyframeGenerationProvider()
    service, storage, _ = await _service(tmp_path, generator)
    storyboard = await service.generate(shot_contract=_contract())
    before = set((tmp_path / "assets").rglob("*"))

    with pytest.raises(KeyframeGenerationError, match="already contains"):
        await service.generate(shot_contract=_contract(), storyboard=storyboard)

    assert set((tmp_path / "assets").rglob("*")) == before
    assert len(generator.requests) == 1
