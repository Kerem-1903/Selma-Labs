from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from core.domain.services.wan_checkpoint_codec import (
    canonical_json_bytes,
    job_checksum,
    migrate_v1_envelope,
)
from infrastructure.repositories.local_json_wan_job_repository import (
    LocalJsonWanJobRepository,
)
from infrastructure.storage.local_wan_artifact_store import LocalWanArtifactStore
from tests.unit.test_wan_unattended_worker import make_job


def test_canonical_bytes_are_order_unicode_timestamp_and_float_stable():
    timestamp = datetime(2026, 9, 10, 15, 0, 0, 123456, tzinfo=timezone(timedelta(hours=3)))
    left = {"z": -0.0, "nested": {"unicode": "İçerik 🚀", "time": timestamp}, "value": 1.0}
    right = {"value": 1, "nested": {"time": "2026-09-10T12:00:00.123456Z", "unicode": "İçerik 🚀"}, "z": 0.0}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert job_checksum(left) == job_checksum(right)
    assert b"\\u" not in canonical_json_bytes(left)
    assert canonical_json_bytes({"tiny": 1e-7}) == b'{"tiny":1e-7}'
    assert canonical_json_bytes({"one": 1e20}) == b'{"one":100000000000000000000}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_bytes_reject_non_finite_float(value):
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": value})


@pytest.mark.asyncio
async def test_v1_migration_is_lossless_and_idempotent(tmp_path):
    job = make_job("legacy")
    v1 = {"schema_version": 1, "committed": True, "job": job.to_dict()}
    migrated = migrate_v1_envelope(v1)
    assert migrated["schema_version"] == 2
    assert migrated["job"]["job_id"] == "legacy"
    repo = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "legacy.json").write_text(json.dumps(v1), encoding="utf-8")
    loaded = await repo.get("legacy")
    again = await repo.get("legacy")
    assert loaded.to_dict() == again.to_dict() == job.to_dict()
    assert json.loads((tmp_path / "queue" / "legacy.json").read_text(encoding="utf-8"))["schema_version"] == 2


@pytest.mark.asyncio
async def test_revision_cas_and_checksum_fail_closed(tmp_path):
    repo = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    job = make_job("cas")
    await repo.add(job)
    claimed = await repo.claim_next("GPU-0", 10)
    assert claimed and claimed.revision == 1
    with pytest.raises(ValueError, match="stale writer"):
        await repo.save(claimed.heartbeat(claimed.lease_id or "", claimed.attempt_id or "", claimed.fencing_token, datetime.now(timezone.utc) + timedelta(seconds=10)), expected_revision=0)
    path = tmp_path / "queue" / "cas.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["job"]["priority"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="could not be read"):
        await repo.get("cas")


@pytest.mark.asyncio
async def test_heartbeat_returns_new_revision_and_stale_heartbeat_is_rejected(tmp_path):
    repo = LocalJsonWanJobRepository(tmp_path / "queue", provider_persistent_volume=True)
    await repo.add(make_job("heartbeat"))
    claimed = await repo.claim_next("GPU-0", 10)
    assert claimed
    result = await repo.heartbeat("heartbeat.json", claimed.lease_id or "", claimed.attempt_id or "", claimed.fencing_token, claimed.revision, 10)
    assert result.accepted and result.revision == claimed.revision + 1
    stale = await repo.heartbeat("heartbeat.json", claimed.lease_id or "", claimed.attempt_id or "", claimed.fencing_token, claimed.revision, 10)
    assert not stale.accepted and stale.conflict


@pytest.mark.asyncio
async def test_duplicate_upload_is_reused_and_stale_fence_cannot_promote(tmp_path):
    store = LocalWanArtifactStore(tmp_path / "artifacts")
    data = b"render"
    digest = hashlib.sha256(data).hexdigest()
    first = await store.put_if_absent_or_same("wan/attempts/job/attempt/render.mp4", data, digest, len(data))
    second = await store.put_if_absent_or_same("wan/attempts/job/attempt/render.mp4", data, digest, len(data))
    conflict = await store.put_if_absent_or_same("wan/attempts/job/attempt/render.mp4", b"changed", hashlib.sha256(b"changed").hexdigest(), 7)
    assert first.accepted and second.reused and not conflict.accepted
    await store.register_fencing_token("job", 2)
    assert (await store.promote_if_fenced("wan/attempts/job/attempt/render.mp4", "wan/final/job.mp4", digest, 2)).accepted
    stale = await store.promote_if_fenced("wan/attempts/job/attempt/render.mp4", "wan/final/job.mp4", "other", 1)
    assert not stale.accepted
    head = await store.head("wan/attempts/job/attempt/render.mp4")
    assert head.exists and head.sha256 == digest and head.byte_size == len(data)
