import pytest
from core.domain.entities.candidate.keyframe_candidate import KeyframeCandidate, CandidateStatus
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import SqliteKeyframeCandidateRepository
from core.application.services.candidate.candidate_evaluation_service import CandidateEvaluationService

@pytest.fixture
def repo():
    return SqliteKeyframeCandidateRepository(db_path=":memory:")

@pytest.fixture
def service(repo):
    return CandidateEvaluationService(repository=repo)

@pytest.mark.asyncio
async def test_keyframe_candidate_status_transitions():
    candidate = KeyframeCandidate(
        id="c-1",
        shot_contract_id="s-1",
        storage_key="store/key.png",
        generation_metadata={"seed": 42}
    )
    assert candidate.status == CandidateStatus.PENDING

    candidate.approve()
    assert candidate.status == CandidateStatus.APPROVED
    assert candidate.rejection_reason is None

    candidate.reject("Bad hands", score=2)
    assert candidate.status == CandidateStatus.REJECTED
    assert candidate.rejection_reason == "Bad hands"
    assert candidate.score == 2

    candidate.flag_for_revision("Fix lighting")
    assert candidate.status == CandidateStatus.NEEDS_REVISION
    assert candidate.rejection_reason == "Fix lighting"

@pytest.mark.asyncio
async def test_repository_save_and_retrieve(repo):
    candidate = KeyframeCandidate(
        id="c-1",
        shot_contract_id="s-1",
        storage_key="store/key.png",
        generation_metadata={"seed": 42}
    )
    await repo.save(candidate)

    retrieved = await repo.get_by_id("c-1")
    assert retrieved is not None
    assert retrieved.shot_contract_id == "s-1"
    assert retrieved.generation_metadata["seed"] == 42

    pending = await repo.list_pending()
    assert len(pending) == 1
    assert pending[0].id == "c-1"

@pytest.mark.asyncio
async def test_evaluation_service_quality_gate(service):
    # Register 3 candidates
    await service.register_candidate("s-1", "store/1.png", {"seed": 1})
    c2 = await service.register_candidate("s-1", "store/2.png", {"seed": 2})
    await service.register_candidate("s-1", "store/3.png", {"seed": 3})

    candidates = await service.get_candidates_for_shot("s-1")
    assert len(candidates) == 3

    approved = await service.get_approved_candidate_for_shot("s-1")
    assert approved is None

    # Approve second candidate
    await service.approve_candidate(c2.id)

    approved = await service.get_approved_candidate_for_shot("s-1")
    assert approved is not None
    assert approved.id == c2.id
    assert approved.status == CandidateStatus.APPROVED

@pytest.mark.asyncio
async def test_single_approval_rule(service):
    c1 = await service.register_candidate("s-2", "store/1.png", {"seed": 1})
    c2 = await service.register_candidate("s-2", "store/2.png", {"seed": 2})

    await service.approve_candidate(c1.id)

    with pytest.raises(ValueError, match="already has an approved candidate"):
        await service.approve_candidate(c2.id)

@pytest.mark.asyncio
async def test_score_validation():
    candidate = KeyframeCandidate(
        id="c-1",
        shot_contract_id="s-1",
        storage_key="store/key.png",
        generation_metadata={"seed": 42}
    )
    with pytest.raises(ValueError, match="Score must be between 1 and 5."):
        candidate.reject("Bad hands", score=6)


@pytest.mark.asyncio
async def test_committed_candidate_cannot_be_reviewed_again(service):
    candidate = await service.register_candidate("s-3", "store/1.png", {})
    await service.approve_candidate(candidate.id)
    committed = await service.mark_candidate_committed(candidate.id)

    assert committed.status == CandidateStatus.COMMITTED
    with pytest.raises(ValueError, match="cannot be reviewed again"):
        await service.reject_candidate(candidate.id, "Changed my mind")
