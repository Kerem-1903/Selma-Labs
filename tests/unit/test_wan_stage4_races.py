from __future__ import annotations

import hashlib
import json

import pytest

from core.application.services.wan_attempt_commit_service import WanAttemptCommitService
from core.application.services.wan_job_queue_service import WanJobQueueService
from core.application.services.wan_output_verification_service import (
    WanOutputVerificationService,
)
from core.application.services.wan_worker_service import WanWorkerService
from core.domain.entities.wan_render_job import WanRenderJobStatus
from infrastructure.providers.wan.fake_wan_worker_provider import (
    FakeWanComputeLifecycle,
    FakeWanWorkerProvider,
)
from infrastructure.repositories.local_json_wan_job_repository import (
    LocalJsonWanJobRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage
from infrastructure.storage.local_wan_artifact_store import LocalWanArtifactStore
from tests.unit.test_wan_unattended_worker import UnusedInspector, make_job


@pytest.mark.asyncio
async def test_coordinator_lock_is_exclusive_across_repository_instances(tmp_path):
    first = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    second = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    assert await first.acquire_coordinator_lock("owner-a", 30)
    assert not await second.acquire_coordinator_lock("owner-b", 30)
    await first.release_coordinator_lock("owner-a")
    assert await second.acquire_coordinator_lock("owner-b", 30)


@pytest.mark.asyncio
async def test_stale_commit_rechecks_durable_fence_before_promote(tmp_path):
    repository = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    artifacts = LocalWanArtifactStore(tmp_path / "artifacts")
    await repository.add(make_job("fenced"))
    first = await repository.claim_next("GPU-0", 30)
    assert first
    expired = first.recover_expired_claim()
    await repository.save(expired, expected_revision=first.revision)
    current = await repository.claim_next("GPU-1", 30)
    assert current and current.fencing_token > first.fencing_token
    output = tmp_path / "render.mp4"
    output.write_bytes(b"old-render")
    stale_service = WanAttemptCommitService(repository, artifacts)
    manifest = await stale_service.upload_attempt(first, output)
    with pytest.raises(ValueError, match="stale|lease|fencing"):
        await stale_service.conditional_commit(first, manifest, first.revision)
    assert not (tmp_path / "artifacts" / "wan" / "final" / "fenced.mp4").exists()


@pytest.mark.asyncio
async def test_long_render_heartbeats_before_lease_expires(tmp_path):
    provider = FakeWanWorkerProvider(delays={"long": 0.2})
    storage = LocalFsStorage(str(tmp_path / "assets"))
    repository = LocalJsonWanJobRepository(tmp_path / "queue", checkpoint_storage=storage)
    queue = WanJobQueueService(repository, lease_seconds=0.03)
    await queue.enqueue([make_job("long")])
    worker = WanWorkerService(
        queue,
        provider,
        WanOutputVerificationService(UnusedInspector()),
        storage,
        FakeWanComputeLifecycle(),
        work_directory=tmp_path / "work",
        hard_runtime_seconds=1,
        attempt_commits=WanAttemptCommitService(
            repository, LocalWanArtifactStore(tmp_path / "artifacts")
        ),
    )
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.COMPLETED
    assert jobs[0].revision >= 4


@pytest.mark.asyncio
async def test_promotion_repairs_final_bytes_without_metadata(tmp_path):
    store = LocalWanArtifactStore(tmp_path / "artifacts")
    data = b"recoverable"
    digest = hashlib.sha256(data).hexdigest()
    source = tmp_path / "artifacts" / "wan" / "attempts" / "recover" / "a" / "render.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(data)
    await store.register_fencing_token("recover", 3)
    final = tmp_path / "artifacts" / "wan" / "final" / "recover.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(data)
    result = await store.promote_if_fenced(
        "wan/attempts/recover/a/render.mp4", "wan/final/recover.mp4", digest, 3
    )
    assert result.accepted
    metadata = final.with_name(".recover.mp4.promote.json")
    assert json.loads(metadata.read_text(encoding="utf-8"))["fingerprint"] == digest


@pytest.mark.asyncio
async def test_promotion_repairs_final_bytes_from_metadata_only(tmp_path):
    store = LocalWanArtifactStore(tmp_path / "artifacts")
    data = b"metadata-recovery"
    digest = hashlib.sha256(data).hexdigest()
    source_key = "wan/attempts/recover-meta/a/render.mp4"
    source = tmp_path / "artifacts" / source_key
    source.parent.mkdir(parents=True)
    source.write_bytes(data)
    await store.register_fencing_token("recover-meta", 4)
    final = tmp_path / "artifacts" / "wan" / "final" / "recover-meta.mp4"
    metadata = final.with_name(".recover-meta.mp4.promote.json")
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        json.dumps({"fingerprint": digest, "fencing_token": 4, "source_key": source_key}),
        encoding="utf-8",
    )
    result = await store.promote_if_fenced(
        source_key, "wan/final/recover-meta.mp4", digest, 4
    )
    assert result.accepted
    assert final.read_bytes() == data


@pytest.mark.asyncio
async def test_corrupt_final_bytes_are_not_reused_as_completed(tmp_path):
    store = LocalWanArtifactStore(tmp_path / "artifacts")
    data = b"authoritative-source"
    digest = hashlib.sha256(data).hexdigest()
    source_key = "wan/attempts/corrupt-final/a/render.mp4"
    source = tmp_path / "artifacts" / source_key
    source.parent.mkdir(parents=True)
    source.write_bytes(data)
    await store.register_fencing_token("corrupt-final", 2)
    final = tmp_path / "artifacts" / "wan" / "final" / "corrupt-final.mp4"
    metadata = final.with_name(".corrupt-final.mp4.promote.json")
    final.parent.mkdir(parents=True)
    final.write_bytes(b"tampered")
    metadata.write_text(
        json.dumps({"fingerprint": digest, "fencing_token": 2, "source_key": source_key}),
        encoding="utf-8",
    )
    result = await store.promote_if_fenced(
        source_key, "wan/final/corrupt-final.mp4", digest, 2
    )
    assert not result.accepted
    assert result.conflict == "FINAL_KEY_CONFLICT"
    assert final.read_bytes() == b"tampered"
