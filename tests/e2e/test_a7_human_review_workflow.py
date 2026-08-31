import pytest
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.application.services.candidate.candidate_evaluation_service import CandidateEvaluationService
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.shot_contract import ShotContract
from core.domain.exceptions import KeyframeGenerationError
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import SqliteKeyframeCandidateRepository
from infrastructure.repositories.local_json_shot_storyboard_repository import LocalJsonShotStoryboardRepository
from infrastructure.repositories.local_json_character_bible_repository import LocalJsonCharacterBibleRepository
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort, KeyframeGenerationRequest
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
import typing
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.storage_reference import StorageReference

class MockGenerator(KeyframeGenerationPort):
    def __init__(self):
        self._name = "mock_provider"

    @property
    def name(self) -> str:
        return self._name

    async def generate_keyframe(self, request: KeyframeGenerationRequest) -> GeneratedKeyframe:
        return GeneratedKeyframe(
            image_bytes=b"\x89PNG\r\n\x1a\nmock_data",
            content_type="image/png",
            width=1024,
            height=1024,
            provider_asset_id="mock-asset-123",
            metadata={"reference_asset_ids": list(request.reference_asset_ids)}
        )

class MockStorage(StoragePort):
    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        return StorageReference(key=key, path=f"mock://{key}", size_bytes=len(data))

    async def load(self, key: str) -> bytes:
        return b"mock"

    async def exists(self, key: str) -> bool:
        return True

    def upload_file(self, file_stream: typing.BinaryIO, destination_path: str, content_type: str) -> str:
        return f"mock://{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        return True

    def delete_file(self, file_path: str) -> bool:
        return True

@pytest.fixture
def candidate_repo():
    return SqliteKeyframeCandidateRepository(db_path=":memory:")

@pytest.fixture
def evaluation_service(candidate_repo):
    return CandidateEvaluationService(repository=candidate_repo)

@pytest.fixture
def storyboard_repo(tmp_path):
    return LocalJsonShotStoryboardRepository(str(tmp_path))

@pytest.fixture
def bible_repo(tmp_path):
    return LocalJsonCharacterBibleRepository(str(tmp_path))

@pytest.fixture
def keyframe_service(evaluation_service, storyboard_repo, bible_repo):
    return KeyframeGenerationService(
        generator=MockGenerator(),
        storage=MockStorage(),
        character_bibles=bible_repo,
        storyboards=storyboard_repo,
        candidate_evaluation=evaluation_service
    )

from core.domain.value_objects.shot_constraints import CameraConstraints, ActionConstraints, VisualConstraints

@pytest.mark.asyncio
async def test_a7_human_review_workflow(keyframe_service, evaluation_service):
    # 1. Setup ShotContract
    contract = ShotContract(
        id="shot-123",
        camera_constraints=CameraConstraints(angle="wide", lens="35mm", movement="static"),
        action_constraints=ActionConstraints(primary_action="walking"),
        visual_constraints=VisualConstraints(lighting="dark", environment_style="cyberpunk", weather="rain")
    )

    # 2. Generate multiple candidates
    await keyframe_service.generate_candidates(shot_contract=contract, count=3)

    # 3. Verify candidates are in PENDING state
    candidates = await evaluation_service.get_candidates_for_shot(contract.id)
    assert len(candidates) == 3
    assert all(c.status == CandidateStatus.PENDING for c in candidates)

    # 4. Attempt to commit to storyboard before approval (should fail)
    with pytest.raises(KeyframeGenerationError, match="No approved candidate found"):
        await keyframe_service.commit_approved_candidate(contract.id)

    # 5. Review process: reject first, approve second
    await evaluation_service.reject_candidate(candidates[0].id, reason="Bad hands", score=2)
    await evaluation_service.approve_candidate(candidates[1].id)

    # 6. Verify single approval rule
    with pytest.raises(ValueError, match="already has an approved candidate"):
        await evaluation_service.approve_candidate(candidates[2].id)

    # 7. Commit approved candidate to storyboard
    storyboard = await keyframe_service.commit_approved_candidate(contract.id)

    # 8. Verify storyboard contains only the approved frame
    assert len(storyboard.frames) == 1
    assert storyboard.frames[0].storage_key == candidates[1].storage_key
