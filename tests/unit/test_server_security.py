from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

import server


def test_server_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("SELMA_SERVER_HOST", raising=False)
    monkeypatch.delenv("SELMA_ALLOW_NETWORK", raising=False)

    assert server.resolve_server_host() == "127.0.0.1"


def test_server_rejects_network_binding_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SELMA_SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("SELMA_ALLOW_NETWORK", raising=False)

    with pytest.raises(RuntimeError, match="SELMA_ALLOW_NETWORK"):
        server.resolve_server_host()


@pytest.mark.asyncio
async def test_video_endpoint_rejects_unregistered_job():
    job_id = str(uuid.uuid4())

    with pytest.raises(HTTPException) as raised:
        await server.get_video_artifact(job_id)

    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_video_endpoint_serves_only_registered_completed_mp4(tmp_path):
    job_id = str(uuid.uuid4())
    artifact = tmp_path / "final.mp4"
    artifact.write_bytes(b"video")
    server.JOB_STATUS[job_id] = {"status": "completed"}
    server.VIDEO_ARTIFACTS[job_id] = artifact

    try:
        response = await server.get_video_artifact(job_id)
    finally:
        server.JOB_STATUS.pop(job_id, None)
        server.VIDEO_ARTIFACTS.pop(job_id, None)

    assert response.path == artifact
    assert response.media_type == "video/mp4"
