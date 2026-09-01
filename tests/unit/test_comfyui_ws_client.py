from __future__ import annotations

import json
from types import SimpleNamespace

import aiohttp
import pytest

from core.domain.exceptions import ProviderError
from infrastructure.providers.motion.comfyui_ws_client import ComfyUIWsClient


class FakeWebSocket:
    def __init__(self, events):
        self.events = iter(events)

    async def receive(self):
        payload = next(self.events)
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(payload))


@pytest.mark.asyncio
async def test_websocket_progress_maps_sampler_events_across_two_passes():
    prompt = {
        "pass1": {"_meta": {"selma_pass": 1}},
        "pass2": {"_meta": {"selma_pass": 2}},
    }
    websocket = FakeWebSocket(
        [
            {"type": "executing", "data": {"prompt_id": "p1", "node": "pass1"}},
            {"type": "progress", "data": {"prompt_id": "p1", "value": 5, "max": 10}},
            {"type": "executing", "data": {"prompt_id": "p1", "node": "pass2"}},
            {"type": "progress", "data": {"prompt_id": "p1", "value": 5, "max": 10}},
            {"type": "executing", "data": {"prompt_id": "p1", "node": None}},
        ]
    )
    progress = []
    client = ComfyUIWsClient("127.0.0.1:8188")

    await client._wait_for_execution(
        websocket,
        prompt_id="p1",
        prompt=prompt,
        progress_callback=progress.append,
    )

    assert progress == [0.25, 0.75, 1.0]


@pytest.mark.asyncio
async def test_websocket_execution_error_becomes_provider_error():
    websocket = FakeWebSocket(
        [
            {
                "type": "execution_error",
                "data": {"prompt_id": "p1", "exception_message": "model missing"},
            }
        ]
    )
    client = ComfyUIWsClient("http://127.0.0.1:8188")

    with pytest.raises(ProviderError, match="model missing"):
        await client._wait_for_execution(
            websocket,
            prompt_id="p1",
            prompt={},
            progress_callback=None,
        )
