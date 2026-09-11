"""ComfyUI memory lifecycle adapter used between tournament variants."""

from __future__ import annotations

import asyncio
import json
import urllib.request


class ComfyUiMemoryReleaser:
    def __init__(self, api_url: str, *, timeout_seconds: float = 15.0) -> None:
        self._api_url = api_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def release(self) -> None:
        await asyncio.to_thread(self._release)

    def _release(self) -> None:
        request = urllib.request.Request(
            f"{self._api_url}/free",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"ComfyUI memory release failed with HTTP {response.status}."
                )
