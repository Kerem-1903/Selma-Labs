"""
ElevenLabsVoiceProvider — concrete VoiceGeneratorPort adapter backed by the
ElevenLabs Text-to-Speech API.

This is the only file in the codebase that knows the ElevenLabs API exists.
Called directly via httpx rather than the elevenlabs SDK: a plain REST call
keeps error handling fully under our control (mapping HTTP status codes to
our typed exception hierarchy) instead of depending on how a third-party
SDK chooses to wrap errors, which is more important here than saving a
handful of lines.
"""
from __future__ import annotations

from io import BytesIO

import httpx
from mutagen.mp3 import MP3

from core.domain.exceptions import (
    InvalidVoiceConfigurationError,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio

API_BASE_URL = "https://api.elevenlabs.io/v1"
REQUEST_TIMEOUT_SECONDS = 60.0


class ElevenLabsVoiceProvider(VoiceGeneratorPort):
    """Synthesizes narration audio using the ElevenLabs API.

    ``voice_name`` as passed to ``generate_voice`` is treated as an
    ElevenLabs voice id (e.g. "21m00Tcm4TlvDq8ikWAM") — ElevenLabs' API
    addresses voices by id, not free-text name.

    Speech timing (Sprint 2.1): this implementation currently leaves
    GeneratedAudio.segments empty. ElevenLabs does offer a
    "with-timestamps" endpoint variant that returns character-level
    alignment; wiring that in later means switching the request URL and
    building SpeechSegment entries from the response here — no change to
    VoiceGeneratorPort, VoiceService, or VoiceTrack is needed for that.
    """

    def __init__(self, api_key: str, model_id: str = "eleven_multilingual_v2") -> None:
        if not api_key:
            raise ProviderAuthError(
                "ElevenLabs API key is missing. Set ELEVENLABS_API_KEY in your .env file."
            )
        self._api_key = api_key
        self._model_id = model_id

    async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio:
        voice_id = voice_name
        url = f"{API_BASE_URL}/text-to-speech/{voice_id}"

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url,
                    headers={
                        "xi-api-key": self._api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": self._model_id,
                    },
                    params={"output_format": "mp3_44100_128"},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"ElevenLabs API timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(f"Could not connect to ElevenLabs API: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(f"ElevenLabs API request failed: {exc}") from exc

        self._raise_for_status(response, voice_id)

        audio_bytes = response.content
        duration_seconds, sample_rate = self._read_mp3_metadata(audio_bytes)

        return GeneratedAudio(
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            provider=f"elevenlabs:{self._model_id}",
            voice_name=voice_id,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, voice_id: str) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 401:
            raise ProviderAuthError(f"ElevenLabs API rejected the API key: {response.text}")
        if response.status_code == 429:
            raise ProviderQuotaExceededError(
                f"ElevenLabs API rate limit or quota exceeded: {response.text}"
            )
        if response.status_code in (400, 404, 422):
            raise InvalidVoiceConfigurationError(
                f"ElevenLabs rejected voice id '{voice_id}' or request parameters "
                f"(status {response.status_code}): {response.text}"
            )
        raise ProviderError(
            f"ElevenLabs API returned an error (status {response.status_code}): {response.text}"
        )

    @staticmethod
    def _read_mp3_metadata(audio_bytes: bytes) -> tuple[float, int]:
        try:
            info = MP3(BytesIO(audio_bytes)).info
            return float(info.length), int(info.sample_rate)
        except Exception as exc:  # noqa: BLE001 - any parse failure means unusable audio
            raise ProviderError(
                f"Could not read duration/sample rate from ElevenLabs response: {exc}"
            ) from exc
