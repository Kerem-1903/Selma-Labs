"""Authoritative WAV timing helpers for locked frame timelines."""

from __future__ import annotations

import hashlib
import io
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DialogueTiming:
    audio_seconds: float
    required_frames: int
    allocated_frames: int
    status: str
    padding_frames: int = 0
    overflow_frames: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_seconds": self.audio_seconds,
            "required_frames": self.required_frames,
            "allocated_frames": self.allocated_frames,
            "status": self.status,
            "padding_frames": self.padding_frames,
            "overflow_frames": self.overflow_frames,
        }


class AudioTimingService:
    """Read exact PCM sample counts; never changes the locked shot duration."""

    @staticmethod
    def _duration(file_object: Any) -> float:
        with wave.open(file_object, "rb") as wav:
            rate = wav.getframerate()
            samples = wav.getnframes()
        if rate <= 0:
            raise ValueError("WAV sample rate must be positive.")
        return samples / rate

    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def wav_duration_seconds(cls, path: str | Path) -> float:
        with Path(path).open("rb") as handle:
            return cls._duration(handle)

    @classmethod
    def wav_bytes_duration_seconds(cls, data: bytes) -> float:
        return cls._duration(io.BytesIO(data))

    @staticmethod
    def _timing(seconds: float, *, allocated_frames: int, fps: int) -> DialogueTiming:
        if allocated_frames < 1 or fps < 1:
            raise ValueError("Allocated frames and FPS must be positive.")
        required = math.ceil(seconds * fps)
        if required > allocated_frames:
            return DialogueTiming(
                seconds, required, allocated_frames, "BLOCKED",
                overflow_frames=required - allocated_frames,
            )
        return DialogueTiming(
            seconds, required, allocated_frames, "OK",
            padding_frames=allocated_frames - required,
        )

    @classmethod
    def inspect_dialogue(
        cls,
        path: str | Path,
        *,
        allocated_frames: int,
        fps: int = 24,
    ) -> DialogueTiming:
        return cls._timing(
            cls.wav_duration_seconds(path),
            allocated_frames=allocated_frames,
            fps=fps,
        )

    @classmethod
    def inspect_dialogue_bytes(
        cls,
        data: bytes,
        *,
        allocated_frames: int,
        fps: int = 24,
    ) -> DialogueTiming:
        return cls._timing(
            cls.wav_bytes_duration_seconds(data),
            allocated_frames=allocated_frames,
            fps=fps,
        )
