import pytest
from core.domain.entities.script_candidate import ScriptCandidate, CandidateGroup, CandidateStatus
from infrastructure.repositories.sqlite_candidate_repository import SqliteCandidateRepository

@pytest.fixture
def repo():
    # Use in-memory SQLite for testing to avoid file locks and ensure clean state per test
    return SqliteCandidateRepository(db_path=":memory:")

def test_save_and_retrieve_candidate(repo):
    candidate = ScriptCandidate.create(
        topic="Ahtapotlar",
        language="tr",
        target_duration_seconds=30,
        target_audience="gen-z",
        raw_sources="https://wikipedia.org/octopus",
        verified_claims="Ahtapotların üç kalbi vardır.",
        model_info="selmagpt-8b",
        prompt_version="v1.2",
        initial_script="Biliyor muydunuz, ahtapotların tam 3 kalbi var!",
        content_hash="abc123hash",
        group=CandidateGroup.TRAIN
    )

    repo.save(candidate)

    retrieved = repo.get_by_id(candidate.id)
    assert retrieved is not None
    assert retrieved.id == candidate.id
    assert retrieved.topic == "Ahtapotlar"
    assert retrieved.status == CandidateStatus.PENDING
    assert retrieved.group == CandidateGroup.TRAIN

def test_update_candidate(repo):
    candidate = ScriptCandidate.create(
        topic="Mars",
        language="en",
        target_duration_seconds=60,
        target_audience="all",
        raw_sources="NASA",
        verified_claims="Mars is red.",
        model_info="claude-3-5",
        prompt_version="v2",
        initial_script="Mars is a red planet.",
        content_hash="hash",
    )
    repo.save(candidate)

    # Update fields (e.g. human edited and accepted)
    candidate.revised_script = "Mars, the red planet, is fascinating."
    candidate.status = CandidateStatus.ACCEPTED
    candidate.scores.hook = 9.5
    candidate.reasoning = "Good hook, but needed more flow."
    repo.save(candidate)

    retrieved = repo.get_by_id(candidate.id)
    assert retrieved.revised_script == "Mars, the red planet, is fascinating."
    assert retrieved.status == CandidateStatus.ACCEPTED
    assert retrieved.scores.hook == 9.5
    assert retrieved.reasoning == "Good hook, but needed more flow."

def test_list_by_status(repo):
    c1 = ScriptCandidate.create(topic="T1", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s1", content_hash="h1")
    c2 = ScriptCandidate.create(topic="T2", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s2", content_hash="h2")
    c3 = ScriptCandidate.create(topic="T3", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s3", content_hash="h3")

    c1.status = CandidateStatus.ACCEPTED
    c2.status = CandidateStatus.REJECTED
    c3.status = CandidateStatus.ACCEPTED

    repo.save(c1)
    repo.save(c2)
    repo.save(c3)

    accepted = repo.list_by_status(CandidateStatus.ACCEPTED)
    assert len(accepted) == 2
    assert set(c.id for c in accepted) == {c1.id, c3.id}

def test_get_exportable_training_data_prevents_holdout_leakage(repo):
    # Setup candidates in different groups and statuses
    # 1. Accepted, Train -> Should be exported
    c_train = ScriptCandidate.create(topic="Train", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s1", content_hash="h1", group=CandidateGroup.TRAIN)
    c_train.status = CandidateStatus.ACCEPTED

    # 2. Published, Validation -> Should be exported
    c_val = ScriptCandidate.create(topic="Val", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s2", content_hash="h2", group=CandidateGroup.VALIDATION)
    c_val.status = CandidateStatus.PUBLISHED

    # 3. Accepted, Holdout -> MUST NOT BE EXPORTED
    c_holdout = ScriptCandidate.create(topic="Holdout", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s3", content_hash="h3", group=CandidateGroup.HOLDOUT)
    c_holdout.status = CandidateStatus.ACCEPTED

    # 4. Pending, Train -> Should not be exported (only Accepted/Published)
    c_pending = ScriptCandidate.create(topic="Pending", language="tr", target_duration_seconds=30, target_audience="all", raw_sources="src", verified_claims="claims", model_info="m", prompt_version="v", initial_script="s4", content_hash="h4", group=CandidateGroup.TRAIN)
    c_pending.status = CandidateStatus.PENDING

    repo.save(c_train)
    repo.save(c_val)
    repo.save(c_holdout)
    repo.save(c_pending)

    exportable = repo.get_exportable_training_data()

    assert len(exportable) == 2
    exported_ids = set(c.id for c in exportable)
    assert c_train.id in exported_ids
    assert c_val.id in exported_ids

    # Critical data leakage check
    assert c_holdout.id not in exported_ids

    # State check
    assert c_pending.id not in exported_ids
