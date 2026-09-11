from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.application.services.wan_attempt_commit_service import WanAttemptCommitService
from core.application.services.wan_budget_guard import WanBudgetGuard
from core.application.services.wan_job_queue_service import WanJobQueueService
from core.application.services.wan_output_verification_service import (
    WanOutputVerificationService,
)
from core.application.services.wan_worker_service import WanWorkerService
from core.domain.entities.wan_render_job import (
    WanQualityError,
    WanRenderJob,
    WanRenderJobStatus,
    WanTechnicalError,
)
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.value_objects.wan22_animation_package import Wan22AnimationPackage
from core.domain.value_objects.wan22_render_profile import (
    Wan22RenderProfile,
    WanPostprocess,
)
from infrastructure.providers.wan.fake_wan_worker_provider import (
    FakeWanComputeLifecycle,
    FakeWanWorkerProvider,
)
from infrastructure.repositories.local_json_wan_job_repository import (
    LocalJsonWanJobRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage
from infrastructure.storage.local_wan_artifact_store import LocalWanArtifactStore


class UnusedInspector(MediaInspectionPort):
    async def inspect(self, video_path: str):
        raise AssertionError("Fake results provide their inspection directly.")

    async def extract_frame(self, video_path: str, output_path: str, timestamp_seconds: float):
        raise NotImplementedError


def make_job(
    job_id: str,
    *,
    profile: Wan22RenderProfile | None = None,
    max_attempts: int = 3,
    fallback: bool = False,
) -> WanRenderJob:
    profile = profile or Wan22RenderProfile.draft_16fps()
    package = Wan22AnimationPackage(
        shot_id=job_id,
        source_image_key=f"sources/{job_id}.png",
        source_image_hash="a" * 64,
        motion_prompt="cinematic motion",
        negative_prompt="flicker",
        seed=1,
        frame_count=profile.frame_count,
        fps=profile.fps,
        width=832,
        height=480,
        workflow_hash="b" * 64,
        model_revision="wan22-pinned",
        output_video_key=f"wan22/{job_id}.mp4",
    )
    return WanRenderJob(
        job_id=job_id,
        package=package,
        profile=profile,
        max_attempts=max_attempts,
        allow_step_fallback=fallback,
        fallback_profile=Wan22RenderProfile.final_24fps() if fallback else None,
    )


def build_worker(tmp_path: Path, provider, *, budget=None, runtime=2.0):
    storage = LocalFsStorage(str(tmp_path / "persistent-assets"))
    repository = LocalJsonWanJobRepository(
        tmp_path / "provider-volume" / "queue", checkpoint_storage=storage
    )
    queue = WanJobQueueService(repository, lease_seconds=0.05)
    lifecycle = FakeWanComputeLifecycle()
    worker = WanWorkerService(
        queue,
        provider,
        WanOutputVerificationService(UnusedInspector()),
        storage,
        lifecycle,
        work_directory=tmp_path / "cache" / "wan-worker",
        hard_runtime_seconds=runtime,
        budget=budget,
        attempt_commits=WanAttemptCommitService(
            repository, LocalWanArtifactStore(tmp_path / "wan-artifacts")
        ),
    )
    return worker, queue, repository, lifecycle


def test_profiles_lock_source_contract_separately_from_final_timeline():
    draft = Wan22RenderProfile.draft_16fps()
    final = Wan22RenderProfile.final_24fps()
    assert (draft.frame_count, draft.fps, draft.steps, draft.postprocess) == (
        81, 16, 4, WanPostprocess.INTERPOLATE_TO_24
    )
    assert (final.frame_count, final.fps, final.steps, final.postprocess) == (
        121, 24, 40, WanPostprocess.NONE
    )


@pytest.mark.asyncio
async def test_five_jobs_use_one_dynamic_queue_and_long_job_does_not_block_other_slot(tmp_path):
    provider = FakeWanWorkerProvider(delays={"job-0": 0.08})
    worker, queue, _, lifecycle = build_worker(tmp_path, provider)
    await queue.enqueue([make_job(f"job-{index}") for index in range(5)])
    jobs = await worker.run(slot_count=2)
    assert all(job.status == WanRenderJobStatus.COMPLETED for job in jobs)
    assert {slot for _, slot, _ in provider.claims} == {"GPU-0", "GPU-1"}
    assert len({job_id for job_id, _, _ in provider.claims}) == 5
    assert lifecycle.stop_calls == 1


@pytest.mark.asyncio
async def test_completed_jobs_are_skipped_after_repository_restart(tmp_path):
    provider = FakeWanWorkerProvider()
    worker, queue, _, _ = build_worker(tmp_path, provider)
    await queue.enqueue([make_job("done")])
    await worker.run(slot_count=1)
    restarted = LocalJsonWanJobRepository(
        tmp_path / "provider-volume" / "queue",
        checkpoint_storage=LocalFsStorage(str(tmp_path / "persistent-assets")),
    )
    restarted_queue = WanJobQueueService(restarted)
    assert await restarted_queue.enqueue([make_job("done")]) == 0
    assert (await restarted.get("done")).status == WanRenderJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_object_storage_index_recovers_queue_when_local_cache_is_empty(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "object-storage"))
    first = LocalJsonWanJobRepository(tmp_path / "cache-a", checkpoint_storage=storage)
    await first.add(make_job("durable"))
    restarted = LocalJsonWanJobRepository(tmp_path / "cache-b", checkpoint_storage=storage)
    jobs = await restarted.list()
    assert [job.job_id for job in jobs] == ["durable"]
    assert jobs[0].status == WanRenderJobStatus.PENDING


@pytest.mark.asyncio
async def test_expired_running_job_is_reclaimed_after_crash(tmp_path):
    repository = LocalJsonWanJobRepository(
        tmp_path / "provider-volume", provider_persistent_volume=True
    )
    await repository.add(make_job("crashed"))
    first = await repository.claim_next("GPU-0", 0.001)
    assert first and first.status == WanRenderJobStatus.RUNNING
    await asyncio.sleep(0.01)
    second = await repository.claim_next("GPU-1", 1)
    assert second and second.job_id == first.job_id
    assert second.claimed_by == "GPU-1"
    assert second.attempt_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["TIMEOUT", "BROKEN_MP4", "WRONG_FPS", "WRONG_FRAME_COUNT"])
async def test_technical_failures_retry_same_profile(tmp_path, error):
    provider = FakeWanWorkerProvider({"retry": [error, "SUCCESS"]})
    worker, queue, _, _ = build_worker(tmp_path, provider)
    await queue.enqueue([make_job("retry")])
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.COMPLETED
    assert provider.calls["retry"] == 2
    assert [profile for _, _, profile in provider.claims] == ["draft_16fps", "draft_16fps"]


@pytest.mark.asyncio
async def test_quality_failure_requires_human_review(tmp_path):
    provider = FakeWanWorkerProvider({"quality": ["IDENTITY_DRIFT"]})
    worker, queue, _, _ = build_worker(tmp_path, provider)
    await queue.enqueue([make_job("quality")])
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.HUMAN_REVIEW_REQUIRED
    assert jobs[0].quality_error == WanQualityError.IDENTITY_DRIFT


def test_unpermitted_four_to_forty_step_transition_is_rejected():
    job = make_job("locked")
    active = job.claim("GPU-0", job.created_at)
    with pytest.raises(ValueError, match="does not allow"):
        active.use_fallback()


@pytest.mark.asyncio
async def test_explicit_four_to_forty_step_fallback_works_after_attempts_exhausted(tmp_path):
    provider = FakeWanWorkerProvider({"fallback": ["TIMEOUT", "SUCCESS"]})
    worker, queue, _, _ = build_worker(tmp_path, provider)
    await queue.enqueue([make_job("fallback", max_attempts=1, fallback=True)])
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.COMPLETED
    assert jobs[0].profile == Wan22RenderProfile.final_24fps()
    assert [profile for _, _, profile in provider.claims] == ["draft_16fps", "final_24fps"]


@pytest.mark.asyncio
async def test_output_cannot_complete_until_persistent_save_succeeds(tmp_path):
    class RejectArtifactStore(LocalWanArtifactStore):
        async def put_if_absent_or_same(self, key, data, sha256, byte_size):
            raise OSError("persistent store unavailable")

    provider = FakeWanWorkerProvider()
    repository = LocalJsonWanJobRepository(
        tmp_path / "provider-volume", provider_persistent_volume=True
    )
    queue = WanJobQueueService(repository)
    lifecycle = FakeWanComputeLifecycle()
    worker = WanWorkerService(
        queue, provider, WanOutputVerificationService(UnusedInspector()),
        LocalFsStorage(str(tmp_path / "assets")), lifecycle,
        work_directory=tmp_path / "cache", hard_runtime_seconds=1,
        attempt_commits=WanAttemptCommitService(
            repository, RejectArtifactStore(tmp_path / "wan-artifacts")
        ),
    )
    await queue.enqueue([make_job("no-persist", max_attempts=1)])
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.FAILED
    assert jobs[0].output_storage_key is None


@pytest.mark.asyncio
async def test_budget_stops_new_claims_and_does_not_auto_stop_nonempty_queue(tmp_path):
    provider = FakeWanWorkerProvider()
    worker, queue, _, lifecycle = build_worker(
        tmp_path, provider, budget=WanBudgetGuard(max_started_attempts=1)
    )
    await queue.enqueue([make_job("budget-a"), make_job("budget-b")])
    jobs = await worker.run(slot_count=2)
    assert sum(job.status == WanRenderJobStatus.COMPLETED for job in jobs) == 1
    assert sum(job.status == WanRenderJobStatus.PENDING for job in jobs) == 1
    assert lifecycle.stop_calls == 0


@pytest.mark.asyncio
async def test_hard_runtime_cancels_job_as_timeout(tmp_path):
    provider = FakeWanWorkerProvider(delays={"slow": 0.1})
    worker, queue, _, _ = build_worker(tmp_path, provider, runtime=0.005)
    await queue.enqueue([make_job("slow", max_attempts=1)])
    jobs = await worker.run(slot_count=1)
    assert jobs[0].status == WanRenderJobStatus.FAILED
    assert jobs[0].technical_error == WanTechnicalError.TIMEOUT


@pytest.mark.asyncio
async def test_atomic_claim_never_assigns_one_job_to_two_slots(tmp_path):
    repository = LocalJsonWanJobRepository(
        tmp_path / "provider-volume", provider_persistent_volume=True
    )
    await repository.add(make_job("one"))
    claims = await asyncio.gather(
        repository.claim_next("GPU-0", 10),
        repository.claim_next("GPU-1", 10),
    )
    assert sum(claim is not None for claim in claims) == 1
