"""Provider-free Wan worker composition for tests and local pre-GPU runs."""

from __future__ import annotations

from pathlib import Path

from core.application.services.wan_attempt_commit_service import WanAttemptCommitService
from core.application.services.wan_job_queue_service import WanJobQueueService
from core.application.services.wan_output_verification_service import (
    WanOutputVerificationService,
)
from core.application.services.wan_worker_service import WanWorkerService
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.wan_compute_lifecycle_port import WanComputeLifecyclePort
from core.domain.ports.wan_worker_provider_port import WanWorkerProviderPort
from infrastructure.repositories.local_json_wan_job_repository import (
    LocalJsonWanJobRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage
from infrastructure.storage.local_wan_artifact_store import LocalWanArtifactStore


def build_wan_worker(
    *,
    provider: WanWorkerProviderPort,
    lifecycle: WanComputeLifecyclePort,
    inspector: MediaInspectionPort,
    checkpoint_root: str | Path,
    artifact_root: str | Path,
    output_root: str | Path,
    work_directory: str | Path,
    lease_seconds: float = 3600.0,
    hard_runtime_seconds: float = 3600.0,
    checkpoint_storage: StoragePort | None = None,
) -> WanWorkerService:
    output_storage = LocalFsStorage(str(output_root))
    repository = LocalJsonWanJobRepository(
        checkpoint_root,
        checkpoint_storage=checkpoint_storage,
        provider_persistent_volume=checkpoint_storage is None,
    )
    queue = WanJobQueueService(repository, lease_seconds=lease_seconds)
    artifacts = LocalWanArtifactStore(artifact_root)
    commits = WanAttemptCommitService(repository, artifacts)
    return WanWorkerService(
        queue,
        provider,
        WanOutputVerificationService(inspector),
        output_storage,
        lifecycle,
        work_directory=work_directory,
        hard_runtime_seconds=hard_runtime_seconds,
        attempt_commits=commits,
    )
