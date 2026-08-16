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

import base64
from io import BytesIO
import re

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
from core.domain.value_objects.speech_segment import SpeechSegment
from core.domain.value_objects.voice_direction import VoiceDirection

API_BASE_URL = "https://api.elevenlabs.io/v1"
REQUEST_TIMEOUT_SECONDS = 60.0


class ElevenLabsVoiceProvider(VoiceGeneratorPort):
    """Synthesizes narration audio using the ElevenLabs API.

    ``voice_name`` as passed to ``generate_voice`` is treated as an
    ElevenLabs voice id (e.g. "21m00Tcm4TlvDq8ikWAM") — ElevenLabs' API
    addresses voices by id, not free-text name.

    Uses ElevenLabs' timestamp endpoint and converts character alignment to
    exact word segments. Downstream captions can therefore follow the
    approved narration without a second transcription pass.
    """

    def __init__(
        self,
        api_key: str,
        model_id: str = "eleven_multilingual_v2",
        stability: float = 0.35,
        similarity_boost: float = 0.8,
        style: float = 0.45,
        speed: float = 1.05,
        use_speaker_boost: bool = True,
    ) -> None:
        if not api_key:
            raise ProviderAuthError(
                "ElevenLabs API key is missing. Set ELEVENLABS_API_KEY in your .env file."
            )
        self._api_key = api_key
        self._model_id = model_id
        for name, value in (
            ("stability", stability),
            ("similarity_boost", similarity_boost),
            ("style", style),
        ):
            if not 0.0 <= value <= 1.0:
                raise InvalidVoiceConfigurationError(
                    f"ElevenLabs {name} must be between 0.0 and 1.0."
                )
        if not 0.7 <= speed <= 1.2:
            raise InvalidVoiceConfigurationError(
                "ElevenLabs speed must be between 0.7 and 1.2."
            )
        self._voice_settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": speed,
            "use_speaker_boost": use_speaker_boost,
        }

    async def generate_voice(
        self,
        text: str,
        voice_name: str,
        *,
        direction: VoiceDirection | None = None,
    ) -> GeneratedAudio:
        voice_id = voice_name
        url = f"{API_BASE_URL}/text-to-speech/{voice_id}/with-timestamps"

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url,
                    headers={
                        "xi-api-key": self._api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": self._model_id,
                        "voice_settings": self._settings_for_direction(direction),
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

        try:
            payload = response.json()
            audio_bytes = base64.b64decode(payload["audio_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                f"ElevenLabs timestamp response was invalid: {exc}"
            ) from exc
        duration_seconds, sample_rate = self._read_mp3_metadata(audio_bytes)
        segments = self._word_segments(payload.get("alignment"))

        return GeneratedAudio(
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            provider=f"elevenlabs:{self._model_id}",
            voice_name=voice_id,
            segments=segments,
        )

    def _settings_for_direction(
        self,
        direction: VoiceDirection | None,
    ) -> dict[str, float | bool]:
        settings = dict(self._voice_settings)
        if direction is not None:
            settings.update(
                {
                    "stability": direction.stability,
                    "style": direction.style,
                    "speed": direction.speed,
                }
            )
        return settings

    @staticmethod
    def _word_segments(alignment: object) -> list[SpeechSegment]:
        if not isinstance(alignment, dict):
            return []
        characters = alignment.get("characters")
        starts = alignment.get("character_start_times_seconds")
        ends = alignment.get("character_end_times_seconds")
        if not (
            isinstance(characters, list)
            and isinstance(starts, list)
            and isinstance(ends, list)
            and len(characters) == len(starts) == len(ends)
        ):
            return []
        text = "".join(str(character) for character in characters)
        segments: list[SpeechSegment] = []
        for match in re.finditer(r"\S+", text):
            first = match.start()
            last = match.end() - 1
            try:
                start = float(starts[first])
                end = float(ends[last])
            except (TypeError, ValueError, IndexError):
                continue
            if end <= start:
                continue
            segments.append(SpeechSegment(match.group(0), start, end))
        return segments

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
