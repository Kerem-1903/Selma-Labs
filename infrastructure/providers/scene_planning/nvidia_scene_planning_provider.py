from __future__ import annotations

from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient
from infrastructure.providers.scene_planning.claude_scene_planning_provider import (
    ClaudeScenePlanningProvider,
    SYSTEM_PROMPT,
)


class NvidiaScenePlanningProvider(ScenePlanningPort):
    """Plans visual scenes through NVIDIA's chat endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 30.0,
        client: NvidiaChatClient | None = None,
    ) -> None:
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self._model = model

    @property
    def provider_identity(self) -> str:
        return f"nvidia:{self._model}"

    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        raw_text = await self._client.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": narration_text},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        return ClaudeScenePlanningProvider._parse_response(raw_text)
