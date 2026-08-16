from __future__ import annotations

from core.domain.entities.script import Script
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient
from infrastructure.providers.script.claude_script_provider import (
    SYSTEM_PROMPT,
    WORDS_PER_MINUTE_TARGET,
)


class NvidiaScriptProvider(ScriptGeneratorPort):
    """Generates narration scripts through NVIDIA's chat endpoint."""

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

    async def generate_script(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str | None = None,
    ) -> Script:
        words_target = int((target_duration_seconds / 60) * WORDS_PER_MINUTE_TARGET)
        prompt = (
            f"Topic: {topic}\n"
            f"Target spoken duration: {target_duration_seconds} seconds "
            f"(approximately {words_target} words at a natural narration pace).\n"
            f"Output language: {language or 'the language used by the topic'}.\n"
            "Narrative contract: open with a precise curiosity or consequence hook; "
            "if the topic asks why, include an explicit causal answer; if it asks how, "
            "include an explicit mechanism; add no generic invitations or praise; "
            "end on the strongest answer or consequence.\n"
            "Write the narration script now."
        )
        text = await self._client.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.4,
        )
        return Script.create(
            topic=topic,
            full_text=text,
            target_duration_seconds=target_duration_seconds,
            provider_used=f"nvidia:{self._model}",
        )
