"""
CachingVoiceProvider — a VoiceGeneratorPort decorator that transparently
caches generated audio.

Deliberately a Decorator around the Port, not a change to VoiceService: the
application layer must not need to know caching exists (per the Sprint 2.1
requirement). VoiceService is constructed with a VoiceGeneratorPort exactly
as before; whether that instance is a bare ElevenLabsVoiceProvider or one
wrapped in this cache is decided entirely in config/provider_registry.py.

No separate CachePort abstraction was introduced for this: caching here is
an internal performance optimization of one decorator, not a pluggable
business capability anything else in the system needs to swap independently.
If that changes (e.g. a shared Redis cache across multiple workers becomes
necessary), extracting a CachePort at that point is a small, contained
change — same reasoning as the "don't build a state machine library until
the state machine is actually non-linear" call in Architecture v1.

Cache key = SHA256(provider_identity | voice_name | script_text). Identical
script + voice + provider configuration reuses the previous audio; anything
different is a cache miss.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.speech_segment import SpeechSegment

logger = logging.getLogger("selma.voice_cache")


class CachingVoiceProvider(VoiceGeneratorPort):
    """Wraps another VoiceGeneratorPort with a transparent on-disk cache."""

    def __init__(self, inner: VoiceGeneratorPort, cache_dir: str, provider_identity: str) -> None:
        self._inner = inner
        self._cache_dir = Path(cache_dir)
        self._provider_identity = provider_identity

    async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio:
        cache_key = self._compute_key(text, voice_name)

        cached = self._read_cache(cache_key)
        if cached is not None:
            logger.info("voice_cache_hit", extra={"cache_key": cache_key})
            return cached

        logger.info("voice_cache_miss", extra={"cache_key": cache_key})
        # Errors from the inner provider (auth, timeout, quota, etc.)
        # propagate unchanged — caching must never mask or alter them.
        audio = await self._inner.generate_voice(text=text, voice_name=voice_name)

        self._write_cache(cache_key, audio)
        return audio

    def _compute_key(self, text: str, voice_name: str) -> str:
        payload = f"{self._provider_identity}|{voice_name}|{text}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _read_cache(self, key: str) -> Optional[GeneratedAudio]:
        meta_path = self._cache_dir / f"{key}.json"
        audio_path = self._cache_dir / f"{key}.mp3"
        if not meta_path.exists() or not audio_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text())
            audio_bytes = audio_path.read_bytes()
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt/partial cache entry is treated as a miss, not a
            # fatal error — regenerating is always a safe fallback.
            logger.warning("voice_cache_read_failed", extra={"cache_key": key, "error": str(exc)})
            return None

        return GeneratedAudio(
            audio_bytes=audio_bytes,
            duration_seconds=meta["duration_seconds"],
            sample_rate=meta["sample_rate"],
            provider=meta["provider"],
            voice_name=meta["voice_name"],
            segments=[SpeechSegment(**s) for s in meta.get("segments", [])],
        )

    def _write_cache(self, key: str, audio: GeneratedAudio) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            (self._cache_dir / f"{key}.mp3").write_bytes(audio.audio_bytes)
            meta = {
                "duration_seconds": audio.duration_seconds,
                "sample_rate": audio.sample_rate,
                "provider": audio.provider,
                "voice_name": audio.voice_name,
                "segments": [asdict(s) for s in audio.segments],
            }
            (self._cache_dir / f"{key}.json").write_text(json.dumps(meta))
        except OSError as exc:
            # Caching is an optimization, not a correctness requirement —
            # a failed write should not fail the (already-successful)
            # generation that triggered it.
            logger.warning("voice_cache_write_failed", extra={"cache_key": key, "error": str(exc)})
