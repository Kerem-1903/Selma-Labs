from __future__ import annotations

import httpx
import pytest

import server


@pytest.mark.asyncio
async def test_episode_timeline_preview_route_serves_plan_inspector():
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/episode-timeline")

    assert response.status_code == 200
    assert "Episode Timeline Preview" in response.text
    assert "Open plan JSON" in response.text
    assert "READY" in response.text
    assert "PLANNED" in response.text
    assert "BLOCKED" in response.text
    assert "24 FPS Timeline" in response.text


@pytest.mark.asyncio
async def test_episode_timeline_preview_does_not_start_generation_pipeline():
    called = False

    async def forbidden_pipeline(*args, **kwargs):
        nonlocal called
        called = True

    original = server.run_pipeline
    server.run_pipeline = forbidden_pipeline
    try:
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/episode-timeline")
    finally:
        server.run_pipeline = original

    assert response.status_code == 200
    assert called is False
