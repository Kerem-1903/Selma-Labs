"""Local XTTSv2 voice-cloning adapter.

The optional ``TTS`` package is imported only when a generation is requested,
so installations that continue to use ElevenLabs do not pay the import cost.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile

from mutagen.mp3 import MP3

from core.domain.exceptions import (
    InvalidVoiceConfigurationError,
    ProviderError,
)
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.voice_direction import VoiceDirection


class LocalVoiceCloneProvider(VoiceGeneratorPort):
    """Generate narration locally with Coqui XTTSv2 and a reference clip."""

    def __init__(
        self,
        reference_audio_path: str,
        *,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        language: str = "en",
        ffmpeg_binary: str = "ffmpeg",
        gpu: bool = True,
    ) -> None:
        self._reference_audio_path = Path(reference_audio_path).expanduser()
        self._model_name = model_name
        self._language = language.strip().lower()
        self._ffmpeg_binary = ffmpeg_binary
        self._gpu = gpu
        if not self._language:
            raise InvalidVoiceConfigurationError(
                "Local TTS language must not be empty."
            )

    async def generate_voice(
        self,
        text: str,
        voice_name: str,
        *,
        direction: VoiceDirection | None = None,
    ) -> GeneratedAudio:
        if not text.strip():
            raise InvalidVoiceConfigurationError("Local TTS text must not be empty.")
        if not self._reference_audio_path.is_file():
            raise InvalidVoiceConfigurationError(
                "Local TTS reference audio was not found at "
                f"'{self._reference_audio_path}'."
            )
        audio_bytes = await asyncio.to_thread(self._synthesize, text, direction)
        try:
            info = MP3(audio_bytes).info
            duration = float(info.length)
            sample_rate = int(info.sample_rate)
        except Exception as exc:  # noqa: BLE001 - malformed model output
            raise ProviderError(
                f"Local TTS produced invalid MP3 audio: {exc}"
            ) from exc
        return GeneratedAudio(
            audio_bytes=audio_bytes,
            duration_seconds=duration,
            sample_rate=sample_rate,
            provider=f"local-xtts:{self._model_name}",
            voice_name=voice_name or self._reference_audio_path.stem,
        )

    def _synthesize(self, text: str, direction: VoiceDirection | None) -> bytes:
        try:
            from TTS.api import TTS
        except ImportError as exc:
            raise ProviderError(
                "Local voice cloning requires the optional 'TTS' package. "
                "Install it with: pip install TTS"
            ) from exc

        with tempfile.TemporaryDirectory(prefix="selma-xtts-") as directory:
            wav_path = Path(directory) / "narration.wav"
            mp3_path = Path(directory) / "narration.mp3"
            try:
                tts = TTS(model_name=self._model_name, progress_bar=False).to(
                    "cuda" if self._gpu else "cpu"
                )
                kwargs = {
                    "text": text,
                    "speaker_wav": str(self._reference_audio_path),
                    "language": self._language,
                    "file_path": str(wav_path),
                }
                tts.tts_to_file(**kwargs)
                subprocess.run(
                    [
                        self._ffmpeg_binary,
                        "-y",
                        "-i",
                        str(wav_path),
                        "-codec:a",
                        "libmp3lame",
                        "-b:a",
                        "128k",
                        str(mp3_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise ProviderError(
                    f"Local TTS could not find '{exc.filename}'."
                ) from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "").strip()
                raise ProviderError(
                    f"FFmpeg could not encode local TTS audio: {detail}"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - model-specific failures
                raise ProviderError(f"Local XTTS generation failed: {exc}") from exc
            if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
                raise ProviderError("Local XTTS generated no audio output.")
            return mp3_path.read_bytes()