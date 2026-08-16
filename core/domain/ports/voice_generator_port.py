"""
VoiceGeneratorPort — the contract every text-to-speech provider must satisfy.

Same role as ScriptGeneratorPort from Sprint 1: VoiceService depends only on
this interface, never on a concrete provider. Swapping ElevenLabs for OpenAI
TTS, Azure Speech, or a local model means writing one new adapter class and
changing one line in config/provider_registry.py — nothing else changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.voice_direction import VoiceDirection


class VoiceGeneratorPort(ABC):
    """Synthesizes narration audio for a block of text."""

    @abstractmethod
    async def generate_voice(
        self,
        text: str,
        voice_name: str,
        *,
        direction: VoiceDirection | None = None,
    ) -> GeneratedAudio:
        """Synthesize ``text`` as spoken narration audio.

        Args:
            text: The narration text to speak, verbatim.
            voice_name: A provider-specific identifier for the desired
                voice. Depending on the provider this may be a human-
                readable name or an opaque voice id — the port does not
                standardize this, since providers differ.
            direction: Optional provider-neutral tone, tempo, and pause plan.

        Returns:
            A GeneratedAudio value object with raw audio bytes and
            provider-reported metadata.

        Raises:
            ProviderAuthError: Credentials invalid/missing.
            ProviderTimeoutError: Provider accepted the connection but did
                not respond in time.
            ProviderConnectionError: Could not reach the provider at all.
            ProviderQuotaExceededError: Rate limit or quota exceeded.
            InvalidVoiceConfigurationError: ``voice_name`` or generation
                parameters were rejected as invalid by the provider.
            ProviderError: Any other provider-side failure.
        """
        raise NotImplementedError
