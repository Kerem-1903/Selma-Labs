"""
VoiceService — application-layer orchestration for voice generation.

Same division of responsibility as ScriptService in Sprint 1: the provider
adapter's job is "talk to the TTS API and translate the response," this
service's job is "decide whether that output is usable, and persist it."
It depends only on VoiceGeneratorPort and StoragePort — never on a concrete
provider or storage backend.

Scope, per Sprint 2's brief: this module only turns a Script into narrated
audio. It does not generate scripts, plan scenes, generate subtitles, or
touch video — those are other sprints' services, composed together later by
a pipeline orchestrator, not by this class.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import VoiceGenerationError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.application.services.voice_direction_service import VoiceDirectionService
from core.application.services.narration_text_preparation_service import (
    NarrationTextPreparationService,
)

logger = logging.getLogger("selma.voice_service")

AUDIO_CONTENT_TYPE = "audio/mpeg"


class VoiceService:
    """Generates narration audio for a Script via an injected provider,
    and persists it via an injected storage backend."""

    def __init__(
        self,
        provider: VoiceGeneratorPort,
        storage: StoragePort,
        default_voice_name: str,
        direction_service: VoiceDirectionService | None = None,
        text_preparation_service: NarrationTextPreparationService | None = None,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._default_voice_name = default_voice_name
        self._direction_service = direction_service
        self._text_preparation_service = text_preparation_service

    async def generate(self, script: Script, voice_name: Optional[str] = None) -> VoiceTrack:
        """Generate and persist narration audio for ``script``.

        Args:
            script: The Script to narrate. Only ``script.full_text`` is
                spoken; other fields are carried through as metadata.
            voice_name: Optional override for the configured default voice.

        Raises:
            VoiceGenerationError: The script had no text to narrate, or the
                provider's output failed validation (e.g. zero duration).
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota/config failures —
                callers need the typed subclass to decide whether to retry.
            StorageError: Persisting the audio failed.
        """
        if not script.full_text or not script.full_text.strip():
            raise VoiceGenerationError("Script has no narration text to voice.")

        resolved_voice_name = voice_name or self._default_voice_name

        logger.info(
            "voice_generation_started",
            extra={"script_id": script.id, "voice_name": resolved_voice_name},
        )

        direction = (
            self._direction_service.plan(script)
            if self._direction_service is not None
            else None
        )
        preparation = (
            self._text_preparation_service.prepare(script)
            if self._text_preparation_service is not None
            else None
        )
        spoken_text = preparation.spoken_text if preparation is not None else script.full_text
        audio = await self._provider.generate_voice(
            text=spoken_text,
            voice_name=resolved_voice_name,
            direction=direction,
        )

        self._validate_output(audio)

        storage_key = f"voice/{script.id}-{uuid.uuid4()}.mp3"
        reference = await self._storage.save(
            key=storage_key, data=audio.audio_bytes, content_type=AUDIO_CONTENT_TYPE
        )

        voice_track = VoiceTrack.create(
            script_id=script.id,
            duration_seconds=audio.duration_seconds,
            provider=audio.provider,
            voice_name=audio.voice_name,
            sample_rate=audio.sample_rate,
            file_path=reference.path,
            segments=audio.segments,
            direction=direction,
            spoken_text=spoken_text,
            pronunciation_replacements=(
                preparation.replacements if preparation is not None else ()
            ),
        )

        logger.info(
            "voice_generation_completed",
            extra={
                "script_id": script.id,
                "audio_id": voice_track.audio_id,
                "duration_seconds": voice_track.duration_seconds,
            },
        )
        return voice_track

    @staticmethod
    def _validate_output(audio: GeneratedAudio) -> None:
        if not audio.audio_bytes:
            raise VoiceGenerationError("Provider returned empty audio data.")
        if audio.duration_seconds <= 0:
            raise VoiceGenerationError(
                f"Provider returned invalid audio duration: {audio.duration_seconds}s."
            )
