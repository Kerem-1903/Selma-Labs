"""Application boundary for fenced, idempotent Wan artifact commits."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from core.domain.entities.wan_render_job import WanRenderJob, WanRenderJobStatus
from core.domain.ports.wan_artifact_store_port import WanArtifactStorePort
from core.domain.ports.wan_job_repository_port import WanJobRepositoryPort
from core.domain.value_objects.wan_attempt_manifest import WanAttemptManifest


class WanAttemptCommitService:
    def __init__(self, repository: WanJobRepositoryPort, artifacts: WanArtifactStorePort) -> None:
        self._repository = repository
        self._artifacts = artifacts

    async def upload_attempt(self, job: WanRenderJob, output_path: str | Path) -> WanAttemptManifest:
        if (
            job.status not in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}
            or not job.attempt_id
            or not job.lease_id
        ):
            raise ValueError("Wan attempt must be active before artifact upload.")
        data = await asyncio.to_thread(Path(output_path).read_bytes)
        digest = hashlib.sha256(data).hexdigest()
        attempt_key = f"wan/attempts/{job.job_id}/{job.attempt_id}/render.mp4"
        manifest_key = f"wan/attempts/{job.job_id}/{job.attempt_id}/manifest.json"
        manifest = WanAttemptManifest(
            job_id=job.job_id,
            attempt_id=job.attempt_id,
            lease_id=job.lease_id,
            worker_id=job.worker_id or "",
            slot_id=job.slot_id or "",
            fencing_token=job.fencing_token,
            render_storage_key=attempt_key,
            manifest_storage_key=manifest_key,
            byte_size=len(data),
            sha256=digest,
            fingerprint=digest,
        )
        result = await self._artifacts.put_if_absent_or_same(
            attempt_key, data, digest, len(data)
        )
        if not result.accepted:
            raise ValueError(result.conflict or "Wan attempt artifact upload rejected.")
        manifest_bytes = json.dumps(
            manifest.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        manifest_result = await self._artifacts.put_if_absent_or_same(
            manifest_key,
            manifest_bytes,
            hashlib.sha256(manifest_bytes).hexdigest(),
            len(manifest_bytes),
        )
        if not manifest_result.accepted:
            raise ValueError(
                manifest_result.conflict or "Wan attempt manifest upload rejected."
            )
        return manifest

    async def conditional_commit(
        self, job: WanRenderJob, manifest: WanAttemptManifest, expected_revision: int
    ) -> WanRenderJob:
        async def publish_and_complete(current: WanRenderJob) -> WanRenderJob:
            await self._artifacts.register_fencing_token(
                current.job_id, manifest.fencing_token
            )
            final_key = current.package.output_video_key or f"wan/final/{current.job_id}.mp4"
            head = await self._artifacts.head(manifest.render_storage_key)
            if (
                not head.exists
                or head.sha256 != manifest.sha256
                or head.byte_size != manifest.byte_size
            ):
                raise ValueError("Wan attempt artifact HEAD does not match its manifest.")
            promoted = await self._artifacts.promote_if_fenced(
                manifest.render_storage_key,
                final_key,
                manifest.fingerprint or manifest.sha256 or "",
                manifest.fencing_token,
            )
            if not promoted.accepted:
                raise ValueError(promoted.conflict or "Wan final promote rejected.")
            return current.complete(final_key)

        commit = getattr(self._repository, "commit_fenced", None)
        if commit is None:
            raise ValueError("Wan repository does not provide fenced commit authority.")
        return await commit(
            job.job_id,
            manifest.lease_id,
            manifest.attempt_id,
            manifest.fencing_token,
            expected_revision,
            publish_and_complete,
        )
